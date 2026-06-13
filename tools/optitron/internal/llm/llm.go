// Package llm wraps Eino's OpenRouter chat-model component into the structured,
// budget-aware, retrying call optitron needs. The Eino component gives us the
// model client, schema.Message types, strict json_schema structured output, and
// reasoning-effort control; the orchestration around it stays idiomatic Go.
//
// In the PentestGPT-inspired split, this package + the prompt builders are the
// Generator/Reasoner plumbing; gate is the Parser of their output.
package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/cloudwego/eino-ext/components/model/openrouter"
	"github.com/cloudwego/eino/schema"
)

// Prices is the per-1M-token (prompt, completion) table — rough; the budget cap
// is the real guard. Keyed by model slug (with and without an `:online` suffix).
type Price struct{ In, Out float64 }

// Client issues structured OpenRouter calls and tracks spend.
type Client struct {
	APIKey  string
	BaseURL string
	Prices  map[string]Price
	Retries int
	// Notice/Warn are CI loggers (optional; default to no-op).
	Notice func(string)
	Warn   func(string)
}

// New builds a Client with sane defaults.
func New(apiKey, baseURL string, prices map[string]Price) *Client {
	return &Client{
		APIKey:  apiKey,
		BaseURL: baseURL,
		Prices:  prices,
		Retries: 3,
		Notice:  func(string) {},
		Warn:    func(string) {},
	}
}

func ptrInt(i int) *int         { return &i }
func ptrF32(f float32) *float32 { return &f }

// CostOf prices a usage record for a model.
func (c *Client) CostOf(model string, promptTokens, completionTokens int) float64 {
	p, ok := c.Prices[model]
	if !ok {
		// try the slug without an `:online`/provider suffix
		if base := strings.SplitN(model, ":", 2)[0]; base != model {
			p, ok = c.Prices[base]
		}
	}
	if !ok {
		p = Price{In: 0.5, Out: 1.0} // conservative default
	}
	return float64(promptTokens)/1e6*p.In + float64(completionTokens)/1e6*p.Out
}

// CallJSON runs one structured chat completion against `model`, constraining the
// reply to `ns`'s strict JSON schema, and unmarshals it into `out`. It returns
// the USD cost of the call. `effort` is "" for no reasoning, or low|medium|high.
// Retries with exponential backoff on transient failures.
func (c *Client) CallJSON(ctx context.Context, model string, msgs []*schema.Message, ns *namedSchema, maxTokens int, effort string, out any) (float64, error) {
	cfg := &openrouter.Config{
		APIKey:      c.APIKey,
		BaseURL:     c.BaseURL,
		Model:       model,
		MaxTokens:   ptrInt(maxTokens),
		Temperature: ptrF32(0.2),
		TopP:        ptrF32(0.95),
		ResponseFormat: &openrouter.ChatCompletionResponseFormat{
			Type: openrouter.ChatCompletionResponseFormatTypeJSONSchema,
			JSONSchema: &openrouter.ChatCompletionResponseFormatJSONSchema{
				Name:       ns.Name,
				JSONSchema: ns.Schema,
				Strict:     true,
			},
		},
	}
	if effort != "" {
		cfg.Reasoning = &openrouter.Reasoning{Effort: openrouter.Effort(effort)}
	}

	cm, err := openrouter.NewChatModel(ctx, cfg)
	if err != nil {
		return 0, fmt.Errorf("new chat model %s: %w", model, err)
	}

	var lastErr error
	for attempt := 0; attempt < c.Retries; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return 0, ctx.Err()
			case <-time.After(time.Duration(1<<attempt) * time.Second):
			}
		}
		resp, err := cm.Generate(ctx, msgs)
		if err != nil {
			lastErr = err
			continue
		}
		cost := 0.0
		if resp.ResponseMeta != nil && resp.ResponseMeta.Usage != nil {
			u := resp.ResponseMeta.Usage
			cost = c.CostOf(model, u.PromptTokens, u.CompletionTokens)
		}
		if err := unmarshalLenient(resp.Content, out); err != nil {
			lastErr = fmt.Errorf("parse %s: %w", ns.Name, err)
			continue
		}
		return cost, nil
	}
	return 0, fmt.Errorf("CallJSON(%s) failed after %d: %w", model, c.Retries, lastErr)
}

// unmarshalLenient tolerates models that fence JSON in ```...``` or wrap it in
// prose, extracting the outermost object before unmarshaling.
func unmarshalLenient(content string, out any) error {
	s := strings.TrimSpace(content)
	if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		s = strings.TrimPrefix(s, "json")
		if i := strings.Index(s, "```"); i >= 0 {
			s = s[:i]
		}
		s = strings.TrimSpace(s)
	}
	if err := json.Unmarshal([]byte(s), out); err == nil {
		return nil
	}
	start, end := strings.Index(s, "{"), strings.LastIndex(s, "}")
	if start >= 0 && end > start {
		return json.Unmarshal([]byte(s[start:end+1]), out)
	}
	return json.Unmarshal([]byte(s), out) // surface the original error
}
