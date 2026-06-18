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
type Price struct{ In, Out float64 }
type Client struct {
	APIKey  string
	BaseURL string
	Prices  map[string]Price
	Retries int
	Notice func(string)
	Warn   func(string)
}
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
func (c *Client) CostOf(model string, promptTokens, completionTokens int) float64 {
	p, ok := c.Prices[model]
	if !ok {
		if base := strings.SplitN(model, ":", 2)[0]; base != model {
			p, ok = c.Prices[base]
		}
	}
	if !ok {
		p = Price{In: 0.5, Out: 1.0} // conservative default
	}
	return float64(promptTokens)/1e6*p.In + float64(completionTokens)/1e6*p.Out
}
func (c *Client) CallJSON(ctx context.Context, model string, msgs []*schema.Message, ns *NamedSchema, maxTokens int, effort string, out any) (float64, error) {
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