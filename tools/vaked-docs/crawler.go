// Vaked Docs — GitHub API documentation crawler.
// Fetches README, docs/ directory, and wiki content.
// GENESIS_SEAL: 7c242080
package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// ── GitHub API types ──────────────────────────────────────────

type ghContent struct {
	Name        string `json:"name"`
	Type        string `json:"type"` // "file" or "dir"
	Path        string `json:"path"`
	DownloadURL string `json:"download_url"`
	Content     string `json:"content,omitempty"` // base64 for single file
	Encoding    string `json:"encoding,omitempty"`
}

type ghReadme struct {
	Name        string `json:"name"`
	Content     string `json:"content"`
	Encoding    string `json:"encoding"`
	DownloadURL string `json:"download_url"`
}

type ghTreeItem struct {
	Path string `json:"path"`
	Mode string `json:"mode"`
	Type string `json:"type"`
}

type ghTree struct {
	SHA       string        `json:"sha"`
	URL       string        `json:"url"`
	Truncated bool          `json:"truncated"`
	Tree      []ghTreeItem  `json:"tree"`
}



// ── Crawler ───────────────────────────────────────────────────

// Crawler fetches documentation from GitHub repositories.
type Crawler struct {
	Client  *http.Client
	Token   string // optional GitHub token for higher rate limits
	BaseURL string // defaults to "https://api.github.com"
}

// ParseRepoURL extracts owner/repo from a GitHub URL.
// Accepts: https://github.com/owner/repo, https://github.com/owner/repo.git,
//          owner/repo shorthand.
func ParseRepoURL(raw string) (owner, repo string, err error) {
	raw = strings.TrimSuffix(raw, ".git")
	raw = strings.TrimSuffix(raw, "/")

	// owner/repo shorthand
	if !strings.Contains(raw, "://") && !strings.HasPrefix(raw, "git@") {
		parts := strings.SplitN(raw, "/", 3)
		if len(parts) == 2 && parts[0] != "" && parts[1] != "" {
			return parts[0], parts[1], nil
		}
		return "", "", fmt.Errorf("invalid repo URL: %s", raw)
	}

	u, err := url.Parse(raw)
	if err != nil {
		return "", "", err
	}
	parts := strings.SplitN(strings.TrimPrefix(u.Path, "/"), "/", 3)
	if len(parts) < 2 || parts[0] == "" || parts[1] == "" {
		return "", "", fmt.Errorf("cannot extract owner/repo from %s", raw)
	}
	return parts[0], parts[1], nil
}

// NewCrawler creates a crawler. Pass token="" for unauthenticated access (60 req/hr).
func NewCrawler(token string) *Crawler {
	return &Crawler{
		Client:  &http.Client{Timeout: 30 * time.Second},
		Token:   token,
		BaseURL: "https://api.github.com",
	}
}

// FetchCrawl fetches README, docs/, and wiki content for a repo, returning DocEntry slices.
func (c *Crawler) FetchCrawl(owner, repo string) ([]DocEntry, error) {
	var all []DocEntry

	readmeContent, err := c.fetchReadme(owner, repo)
	if err == nil {
		entries := parseMarkdown("README.md", readmeContent)
		all = append(all, entries...)
	}

	docsFiles, err := c.fetchDocsDir(owner, repo)
	if err == nil {
		for _, f := range docsFiles {
			content, err := c.fetchRawContent(f.DownloadURL)
			if err != nil {
				continue
			}
			entries := parseMarkdown(f.Name, content)
			all = append(all, entries...)
		}
	}

	wikiEntries, err := c.fetchWiki(owner, repo)
	if err == nil {
		all = append(all, wikiEntries...)
	}

	if len(all) == 0 {
		return nil, fmt.Errorf("no documentation found for %s/%s", owner, repo)
	}

	return all, nil
}

// fetchReadme fetches the repository README.
func (c *Crawler) fetchReadme(owner, repo string) (string, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/readme", c.BaseURL, owner, repo)
	body, err := c.ghGet(url)
	if err != nil {
		return "", err
	}
	var r ghReadme
	if err := json.Unmarshal(body, &r); err != nil {
		return "", err
	}
	if r.Encoding == "base64" {
		decoded, err := base64.StdEncoding.DecodeString(r.Content)
		if err != nil {
			return "", err
		}
		return string(decoded), nil
	}
	return r.Content, nil
}

// fetchDocsDir fetches files from the docs/ directory.
func (c *Crawler) fetchDocsDir(owner, repo string) ([]ghContent, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/contents/docs", c.BaseURL, owner, repo)
	body, err := c.ghGet(url)
	if err != nil {
		return nil, err // docs/ may not exist
	}

	// Could be a single file or array
	if len(body) > 0 && body[0] == '[' {
		var items []ghContent
		if err := json.Unmarshal(body, &items); err != nil {
			return nil, err
		}
		// Filter to markdown files
		var files []ghContent
		for _, item := range items {
			if item.Type == "file" && (strings.HasSuffix(item.Name, ".md") || strings.HasSuffix(item.Name, ".rst")) {
				files = append(files, item)
			}
		}
		return files, nil
	}

	// Single file response
	var item ghContent
	if err := json.Unmarshal(body, &item); err != nil {
		return nil, err
	}
	if strings.HasSuffix(item.Name, ".md") || strings.HasSuffix(item.Name, ".rst") {
		return []ghContent{item}, nil
	}
	return nil, nil
}

// fetchRawContent downloads raw content from a download_url.
func (c *Crawler) fetchRawContent(downloadURL string) (string, error) {
	if downloadURL == "" {
		return "", fmt.Errorf("empty download URL")
	}
	req, err := http.NewRequest("GET", downloadURL, nil)
	if err != nil {
		return "", err
	}
	// Raw URLs don't need the GitHub API token
	resp, err := c.Client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

// fetchWiki attempts to fetch wiki content via raw.githubusercontent.com.
func (c *Crawler) fetchWiki(owner, repo string) ([]DocEntry, error) {
	// First try the wiki tree via GitHub API (wiki ref)
	treeURL := fmt.Sprintf("%s/repos/%s/%s/git/trees/wiki?recursive=1", c.BaseURL, owner, repo)
	body, err := c.ghGet(treeURL)
	if err != nil {
		// No wiki
		return nil, err
	}

	var tree ghTree
	if err := json.Unmarshal(body, &tree); err != nil {
		return nil, err
	}

	var entries []DocEntry
	for _, item := range tree.Tree {
		if item.Type != "blob" {
			continue
		}
		if !strings.HasSuffix(item.Path, ".md") {
			continue
		}
		// Fetch raw wiki content
		rawURL := fmt.Sprintf("https://raw.githubusercontent.com/wiki/%s/%s/%s", owner, repo, item.Path)
		content, err := c.fetchRawContent(rawURL)
		if err != nil {
			continue
		}
		docEntries := parseMarkdown(item.Path, content)
		entries = append(entries, docEntries...)
	}
	return entries, nil
}

// ghGet performs an authenticated GET to the GitHub API.
func (c *Crawler) ghGet(url string) ([]byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github.v3+json")
	req.Header.Set("User-Agent", "vaked-docs/1.0")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}

	resp, err := c.Client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode == 403 || resp.StatusCode == 429 {
		// Rate limited
		remaining := resp.Header.Get("X-RateLimit-Remaining")
		reset := resp.Header.Get("X-RateLimit-Reset")
		return nil, &RateLimitError{
			StatusCode: resp.StatusCode,
			Remaining:  remaining,
			Reset:      reset,
			Body:       string(body),
		}
	}
	if resp.StatusCode == 404 {
		return nil, fmt.Errorf("not found: %s", url)
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("GitHub API error %d: %s", resp.StatusCode, string(body))
	}

	return body, nil
}

// RateLimitError is returned when GitHub rate limits are hit.
type RateLimitError struct {
	StatusCode int
	Remaining  string
	Reset      string
	Body       string
}

func (e *RateLimitError) Error() string {
	return fmt.Sprintf("GitHub API rate limited (%d): remaining=%s reset=%s", e.StatusCode, e.Remaining, e.Reset)
}

// ParseRateLimitFromHeaders reads rate limit info from response headers.
func ParseRateLimitFromHeaders(remaining, reset string) (int, time.Time, error) {
	rem, err := strconv.Atoi(remaining)
	if err != nil {
		return 0, time.Time{}, err
	}
	unix, err := strconv.ParseInt(reset, 10, 64)
	if err != nil {
		return 0, time.Time{}, err
	}
	return rem, time.Unix(unix, 0), nil
}

// ── Markdown parsing ──────────────────────────────────────────

var (
	headingRe = regexp.MustCompile(`(?m)^(#{1,6})\s+(.+)$`)
	codeBlockRe = regexp.MustCompile("(?s)```.*?\n(.*?)```")
)

// parseMarkdown splits a markdown file into DocEntry sections.
// Each heading creates a DocEntry; content between headings goes into the last heading's entry.
func parseMarkdown(filename, content string) []DocEntry {
	if strings.TrimSpace(content) == "" {
		return nil
	}

	now := time.Now().UTC().Format(time.RFC3339)
	title := extractTitle(filename, content)
	packageID := derivePackageID(filename, title)

	// Split by headings
	type section struct {
		title   string
		content strings.Builder
	}

	var sections []*section
	lines := strings.Split(content, "\n")
	var cur *section

	for _, line := range lines {
		m := headingRe.FindStringSubmatch(line)
		if m != nil {
			cur = &section{title: strings.TrimSpace(m[2])}
			sections = append(sections, cur)
			continue
		}
		if cur == nil {
			// Content before first heading — create an intro section
			cur = &section{title: title}
			sections = append(sections, cur)
		}
		cur.content.WriteString(line)
		cur.content.WriteString("\n")
	}

	if len(sections) == 0 {
		// No headings at all — whole file is one entry
		var sb strings.Builder
		sb.WriteString(strings.TrimSpace(content))
		sb.WriteString("\n")
		sections = []*section{{title: title, content: sb}}
	}

	var entries []DocEntry
	for _, s := range sections {
		text := strings.TrimSpace(s.content.String())
		if text == "" {
			continue
		}
		// Extract code blocks
		var snippets []DocSnippet
		var bodyText strings.Builder

		codeBlocks := codeBlockRe.FindAllStringSubmatch(text, -1)
		remaining := codeBlockRe.ReplaceAllString(text, "")
		bodyText.WriteString(strings.TrimSpace(remaining))

		for _, cb := range codeBlocks {
			if len(cb) >= 2 {
				snippets = append(snippets, DocSnippet{
					Code:  strings.TrimSpace(cb[1]),
					Title: s.title,
				})
			}
		}

		snippets = append(snippets, DocSnippet{
			Content: bodyText.String(),
			Title:   s.title,
		})

		entries = append(entries, DocEntry{
			PackageID: packageID,
			Query:     s.title,
			Snippets:  snippets,
			FetchedAt: now,
		})
	}

	return entries
}

// extractTitle gets the document title from filename or first h1.
func extractTitle(filename, content string) string {
	// Try first h1
	m := headingRe.FindStringSubmatch(content)
	if m != nil && len(m[1]) == 1 {
		return strings.TrimSpace(m[2])
	}
	// Fall back to filename
	name := strings.TrimSuffix(filename, ".md")
	name = strings.TrimSuffix(name, ".rst")
	name = strings.ReplaceAll(name, "-", " ")
	name = strings.ReplaceAll(name, "_", " ")
	return wordsToTitle(name)
}

// derivePackageID creates a stable package identifier from filename and title.
func derivePackageID(filename, title string) string {
	id := strings.ToLower(filename)
	id = strings.TrimSuffix(id, ".md")
	id = strings.TrimSuffix(id, ".rst")
	if id == "readme" || id == "home" {
		id = strings.ToLower(strings.ReplaceAll(title, " ", "-"))
	}
	return id
}




