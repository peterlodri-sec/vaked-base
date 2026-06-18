package introspect
import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)
type LangfuseClient struct {
	Host   string
	Public string
	Secret string
	HTTP   *http.Client
}
func NewLangfuse(host, public, secret string) *LangfuseClient {
	if host == "" || public == "" || secret == "" {
		return nil
	}
	return &LangfuseClient{Host: host, Public: public, Secret: secret,
		HTTP: &http.Client{Timeout: 30 * time.Second}}
}
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
			if resp.StatusCode >= 400 && len(out) == 0 {
				fmt.Printf("::warning::introspect: langfuse %s status=%d, no data — check LANGFUSE_HOST/PUBLIC/SECRET\n", path, resp.StatusCode)
			} else {
				fmt.Printf("::warning::introspect: langfuse %s status=%d\n", path, resp.StatusCode)
			}
			break
		}
		out = append(out, body.Data...)
		if len(body.Data) == 0 || page >= body.Meta.TotalPages {
			break
		}
	}
	return out
}