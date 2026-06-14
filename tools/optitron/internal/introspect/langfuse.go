package introspect

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

// LangfuseClient queries the self-hosted Langfuse public API (HTTP Basic from the
// key pair). It is READ-ONLY observability ingestion — the only "new" capability
// over optitron's core; everything else reuses internal/ledger + internal/llm.
type LangfuseClient struct {
	Host   string
	Public string
	Secret string
	HTTP   *http.Client
}

// NewLangfuse returns a client, or nil if any credential/host is missing (the
// loop then degrades to ledgers + CI only — never crashes).
func NewLangfuse(host, public, secret string) *LangfuseClient {
	if host == "" || public == "" || secret == "" {
		return nil
	}
	return &LangfuseClient{Host: host, Public: public, Secret: secret,
		HTTP: &http.Client{Timeout: 30 * time.Second}}
}

// Query pages a Langfuse public-API list endpoint (e.g. /api/public/observations)
// and returns the merged `data` array. Errors abort that query and return what
// was gathered — the digest tolerates partial/zero telemetry.
func (c *LangfuseClient) Query(path string, params map[string]string, maxPages int) []map[string]any {
	if c == nil {
		return nil
	}
	token := base64.StdEncoding.EncodeToString([]byte(c.Public + ":" + c.Secret))
	var out []map[string]any
	for page := 1; page <= maxPages; page++ {
		q := url.Values{}
		for k, v := range params {
			q.Set(k, v)
		}
		q.Set("page", fmt.Sprintf("%d", page))
		q.Set("limit", "100")
		endpoint := c.Host + path + "?" + q.Encode()

		req, err := http.NewRequest(http.MethodGet, endpoint, nil)
		if err != nil {
			break
		}
		req.Header.Set("Authorization", "Basic "+token)
		resp, err := c.HTTP.Do(req)
		if err != nil {
			fmt.Printf("::warning::introspect: langfuse %s page %d: %v\n", path, page, err)
			break
		}
		var body struct {
			Data []map[string]any `json:"data"`
			Meta struct {
				TotalPages int `json:"totalPages"`
			} `json:"meta"`
		}
		dec := json.NewDecoder(resp.Body)
		decErr := dec.Decode(&body)
		resp.Body.Close()
		if decErr != nil || resp.StatusCode >= 400 {
			fmt.Printf("::warning::introspect: langfuse %s status=%d\n", path, resp.StatusCode)
			break
		}
		out = append(out, body.Data...)
		if len(body.Data) == 0 || page >= body.Meta.TotalPages {
			break
		}
	}
	return out
}
