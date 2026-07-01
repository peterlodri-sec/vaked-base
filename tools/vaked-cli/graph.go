// vaked-cli graph — site graph: discover, crawl, audit cross-references.
//
// Uses Cloudflare API to discover all zones/subdomains, then crawls each
// site to check for 404s, broken links, missing images, and builds a
// cross-reference graph between domains.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

// ── Data structures ──

type SiteNode struct {
	Domain string   `json:"domain"`
	Zone   string   `json:"zone"`
	Pages  []Page   `json:"pages"`
	Broken []Broken `json:"broken,omitempty"`
}

type Page struct {
	URL          string   `json:"url"`
	Status       int      `json:"status"`
	Title        string   `json:"title,omitempty"`
	LinksTo      []string `json:"links_to,omitempty"`
	Images       []string `json:"images,omitempty"`
	BrokenLinks  []string `json:"broken_links,omitempty"`
	BrokenImages []string `json:"broken_images,omitempty"`
}

type Broken struct {
	URL   string `json:"url"`
	Where string `json:"where"` // page URL where the broken link was found
	Code  int    `json:"code,omitempty"`
}

// ── Public entry point ──

func graphCmd(args []string) {
	if len(args) < 1 {
		bail("Usage: vaked-cli graph <discover|audit|crossref|status> [--depth N] [--concurrency N]")
	}
	switch args[0] {
	case "discover":
		graphDiscover(args[1:])
	case "audit":
		graphAudit(args[1:])
	case "crossref":
		graphCrossRef(args[1:])
	case "status":
		graphStatus()
	default:
		bail("unknown graph subcommand: %s", args[0])
	}
}

// ── Flags ──

type graphFlags struct {
	depth       int
	concurrency int
	verbose     bool
}

func parseFlags(args []string) graphFlags {
	f := graphFlags{depth: 1, concurrency: 5}
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--depth":
			if i+1 < len(args) {
				fmt.Sscanf(args[i+1], "%d", &f.depth)
				i++
			}
		case "--concurrency":
			if i+1 < len(args) {
				fmt.Sscanf(args[i+1], "%d", &f.concurrency)
				i++
			}
		case "--verbose", "-v":
			f.verbose = true
		}
	}
	if f.depth < 1 {
		f.depth = 1
	}
	if f.concurrency < 1 {
		f.concurrency = 5
	}
	return f
}

// ── Helpers ──

var (
	hrefRx  = regexp.MustCompile(`(?i)<a[^>]+href\s*=\s*"([^"]+)"`)
	srcRx   = regexp.MustCompile(`(?i)<(?:img|source|video|audio)[^>]+src\s*=\s*"([^"]+)"`)
	titleRx = regexp.MustCompile(`(?i)<title>([^<]+)`)
)

func fetchURL(u string) (int, string, error) {
	client := &http.Client{Timeout: 8 * time.Second}
	req, err := http.NewRequest("GET", u, nil)
	if err != nil {
		return 0, "", err
	}
	req.Header.Set("User-Agent", "vaked-cli-graph/1.0")
	resp, err := client.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1MB max
	if err != nil {
		return resp.StatusCode, "", err
	}
	return resp.StatusCode, string(body), nil
}

func resolveURL(base string, ref string) string {
	if ref == "" || ref == "#" || ref == "/" {
		return ""
	}
	if strings.HasPrefix(ref, "http://") || strings.HasPrefix(ref, "https://") {
		return ref
	}
	if strings.HasPrefix(ref, "//") {
		return "https:" + ref
	}
	if strings.HasPrefix(ref, "/") {
		u, err := url.Parse(base)
		if err != nil {
			return ""
		}
		return u.Scheme + "://" + u.Host + ref
	}
	// Relative path
	baseURL, err := url.Parse(base)
	if err != nil {
		return ""
	}
	refURL, err := url.Parse(ref)
	if err != nil {
		return ""
	}
	return baseURL.ResolveReference(refURL).String()
}

func extractDomain(u string) string {
	parsed, err := url.Parse(u)
	if err != nil {
		return u
	}
	return parsed.Hostname()
}

func shouldSkip(u string) bool {
	skipPrefixes := []string{
		"mailto:", "tel:", "javascript:", "data:",
		"#", "ftp://", "file://",
	}
	for _, p := range skipPrefixes {
		if strings.HasPrefix(u, p) {
			return true
		}
	}
	return false
}

// ── graph discover: crawl a domain and list all pages ──

func graphDiscover(args []string) {
	flags := parseFlags(args)
	requireCF()

	// Fetch all zones and their DNS records
	zones := fetchZones()

	type subdomain struct {
		domain string
		zone   string
	}
	var targets []subdomain

	for _, z := range zones {
		records := fetchDNS(z.ID)
		for _, r := range records {
			// Only A, CNAME, AAAA records that are proxied or point to web servers
			if r.Type == "A" || r.Type == "CNAME" || r.Type == "AAAA" {
				// Skip email/non-web records
				if strings.Contains(r.Name, "_domainkey") ||
					strings.Contains(r.Name, "_dmarc") ||
					strings.Contains(r.Name, "cf-bounce") {
					continue
				}
				targets = append(targets, subdomain{domain: "https://" + r.Name, zone: z.Name})
			}
		}
	}

	fmt.Printf("Discovered %d subdomains across %d zones\n", len(targets), len(zones))
	fmt.Println()

	// Crawl each target
	var mu sync.Mutex
	var nodes []SiteNode
	sem := make(chan struct{}, flags.concurrency)
	var wg sync.WaitGroup

	for _, t := range targets {
		wg.Add(1)
		sem <- struct{}{}
		go func(t subdomain) {
			defer wg.Done()
			defer func() { <-sem }()

			node := SiteNode{Domain: t.domain, Zone: t.zone}
			pages := crawlPage(t.domain, t.domain, flags.depth, flags.concurrency)

			if len(pages) > 0 {
				node.Pages = pages
				// Check for broken links
				for _, p := range pages {
					for _, bl := range p.BrokenLinks {
						node.Broken = append(node.Broken, Broken{URL: bl, Where: p.URL})
					}
					for _, bi := range p.BrokenImages {
						node.Broken = append(node.Broken, Broken{URL: bi, Where: p.URL})
					}
				}
			}

			mu.Lock()
			nodes = append(nodes, node)
			mu.Unlock()

			status := "✓"
			if node.Domain == "" {
				status = "✗"
			}
			fmt.Printf("  %s %s (%d pages", status, t.domain, len(node.Pages))
			if len(node.Broken) > 0 {
				fmt.Printf(", %d broken)", len(node.Broken))
			} else {
				fmt.Print(")")
			}
			fmt.Println()
		}(t)
	}
	wg.Wait()

	fmt.Println()
	fmt.Printf("\nCrawled %d sites. ", len(nodes))

	totalBroken := 0
	for _, n := range nodes {
		totalBroken += len(n.Broken)
	}
	fmt.Printf("Found %d broken links.\n", totalBroken)

	// Output JSON
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(nodes)
}

func crawlPage(baseURL, currentURL string, depth, concurrency int) []Page {
	if depth <= 0 {
		return nil
	}

	code, body, err := fetchURL(currentURL)
	if err != nil || code >= 400 {
		if code == 0 {
			code = 999 // connection error
		}
		return []Page{{URL: currentURL, Status: code}}
	}

	title := ""
	if m := titleRx.FindStringSubmatch(body); len(m) > 1 {
		title = strings.TrimSpace(m[1])
	}

	// Extract links
	links := []string{}
	seen := map[string]bool{}
	for _, m := range hrefRx.FindAllStringSubmatch(body, -1) {
		u := resolveURL(currentURL, m[1])
		if u == "" || seen[u] || shouldSkip(u) {
			continue
		}
		seen[u] = true
		links = append(links, u)
	}

	// Extract images
	images := []string{}
	seenImg := map[string]bool{}
	for _, m := range srcRx.FindAllStringSubmatch(body, -1) {
		u := resolveURL(currentURL, m[1])
		if u == "" || seenImg[u] {
			continue
		}
		seenImg[u] = true
		images = append(images, u)
	}

	page := Page{
		URL:     currentURL,
		Status:  code,
		Title:   title,
		LinksTo: links,
		Images:  images,
	}

	// Check broken links (only check internal links at depth 1 to avoid explosion)
	baseDomain := extractDomain(baseURL)
	if depth > 0 {
		var brokenLinks, brokenImages []string
		sem := make(chan struct{}, concurrency)
		var mu sync.Mutex
		var wg sync.WaitGroup

		checkURL := func(u string, results *[]string) {
			wg.Add(1)
			sem <- struct{}{}
			go func() {
				defer wg.Done()
				defer func() { <-sem }()
				code, _, err := fetchURL(u)
				if err != nil || code >= 400 {
					mu.Lock()
					*results = append(*results, u)
					mu.Unlock()
				}
			}()
		}

		for _, link := range links {
			// Only check links within the same domain to avoid external blast
			if extractDomain(link) == baseDomain || depth > 1 {
				checkURL(link, &brokenLinks)
			}
		}
		for _, img := range images {
			checkURL(img, &brokenImages)
		}
		wg.Wait()

		page.BrokenLinks = brokenLinks
		page.BrokenImages = brokenImages
	}

	// Recurse into internal pages
	if depth > 1 {
		for _, link := range links {
			if extractDomain(link) == baseDomain {
				subPages := crawlPage(baseURL, link, depth-1, concurrency)
				// We just check for broken — don't aggregate sub-pages into this node
				_ = subPages
			}
		}
	}

	return []Page{page}
}

// ── graph audit: comprehensive check of all sites ──

func graphAudit(args []string) {
	flags := parseFlags(args)
	requireCF()

	zones := fetchZones()
	type target struct{ domain, zone string }
	var targets []target

	for _, z := range zones {
		records := fetchDNS(z.ID)
		for _, r := range records {
			if (r.Type == "A" || r.Type == "CNAME" || r.Type == "AAAA") &&
				!strings.Contains(r.Name, "_domainkey") &&
				!strings.Contains(r.Name, "_dmarc") &&
				!strings.Contains(r.Name, "cf-bounce") {
				targets = append(targets, target{
					domain: "https://" + r.Name,
					zone:   z.Name,
				})
			}
		}
	}

	fmt.Printf("Auditing %d subdomains across %d zones…\n\n", len(targets), len(zones))

	type result struct {
		domain  string
		code    int
		title   string
		issues  []string
	}
	results := make([]result, len(targets))
	var wg sync.WaitGroup
	sem := make(chan struct{}, flags.concurrency)

	for i, t := range targets {
		wg.Add(1)
		sem <- struct{}{}
		go func(i int, t target) {
			defer wg.Done()
			defer func() { <-sem }()

			r := result{domain: t.domain}
			code, body, err := fetchURL(t.domain)
			r.code = code
			if err != nil {
				r.issues = append(r.issues, fmt.Sprintf("fetch error: %v", err))
				results[i] = r
				return
			}

			if m := titleRx.FindStringSubmatch(body); len(m) > 1 {
				r.title = strings.TrimSpace(m[1])
			}

			if code >= 400 {
				r.issues = append(r.issues, fmt.Sprintf("HTTP %d", code))
			}

			// Check for common issues
			if strings.Contains(t.domain, "vaked.dev") || strings.Contains(t.domain, "vaked-lang.org") {
				// Check security headers
				req, _ := http.NewRequest("GET", t.domain, nil)
				resp, err := http.DefaultClient.Do(req)
				if err == nil {
					if resp.Header.Get("Strict-Transport-Security") == "" {
						r.issues = append(r.issues, "missing HSTS header")
					}
					if resp.Header.Get("Content-Security-Policy") == "" {
						r.issues = append(r.issues, "missing CSP header")
					}
					resp.Body.Close()
				}
			}

			results[i] = r
		}(i, t)
	}
	wg.Wait()

	// Sort by zone then domain
	sort.Slice(results, func(i, j int) bool {
		if results[i].code != results[j].code {
			return results[i].code < results[j].code
		}
		return results[i].domain < results[j].domain
	})

	fmt.Println("Results:")
	fmt.Println()
	for _, r := range results {
		icon := "✓"
		if r.code >= 400 || len(r.issues) > 0 {
			icon = "✗"
		}
		fmt.Printf("  %s %-50s %d", icon, r.domain, r.code)
		if r.title != "" && flags.verbose {
			fmt.Printf("  %s", r.title)
		}
		fmt.Println()
		for _, issue := range r.issues {
			fmt.Printf("       ⚠ %s\n", issue)
		}
	}

	fmt.Println()
	ok := 0
	bad := 0
	for _, r := range results {
		if r.code < 400 && len(r.issues) == 0 {
			ok++
		} else {
			bad++
		}
	}
	fmt.Printf("Pass: %d  Fail: %d  Total: %d\n", ok, bad, len(results))
}

// ── graph crossref: analyze cross-links between domains ──

func graphCrossRef(args []string) {
	flags := parseFlags(args)
	requireCF()

	zones := fetchZones()
	var domains []string
	for _, z := range zones {
		records := fetchDNS(z.ID)
		for _, r := range records {
			if (r.Type == "A" || r.Type == "CNAME" || r.Type == "AAAA") &&
				!strings.Contains(r.Name, "_domainkey") &&
				!strings.Contains(r.Name, "_dmarc") &&
				!strings.Contains(r.Name, "cf-bounce") {
				domains = append(domains, "https://"+r.Name)
			}
		}
	}

	fmt.Println("=== Cross-Reference Analysis ===")
	fmt.Printf("Analyzing %d domains…\n\n", len(domains))

	type edge struct {
		from string
		to   string
	}
	var edges []edge
	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, flags.concurrency)

	for _, d := range domains {
		wg.Add(1)
		sem <- struct{}{}
		go func(domain string) {
			defer wg.Done()
			defer func() { <-sem }()

			_, body, err := fetchURL(domain)
			if err != nil {
				return
			}

			found := map[string]bool{}
			for _, m := range hrefRx.FindAllStringSubmatch(body, -1) {
				u := resolveURL(domain, m[1])
				if u == "" || shouldSkip(u) {
					continue
				}
				dst := extractDomain(u)
				// Check if destination is one of our known domains
				for _, known := range domains {
					if extractDomain(known) == dst && dst != extractDomain(domain) {
						if !found[dst] {
							found[dst] = true
							mu.Lock()
							edges = append(edges, edge{from: domain, to: known})
							mu.Unlock()
						}
					}
				}
			}
		}(d)
	}
	wg.Wait()

	if len(edges) == 0 {
		fmt.Println("No cross-references found between managed domains.")
		return
	}

	fmt.Println("Cross-references:")
	fmt.Println()
	for _, e := range edges {
		from := extractDomain(e.from)
		to := extractDomain(e.to)
		fmt.Printf("  %-40s → %s\n", from, to)
	}

	fmt.Println()

	// Graph density
	uniqueFrom := map[string]bool{}
	uniqueTo := map[string]bool{}
	for _, e := range edges {
		uniqueFrom[extractDomain(e.from)] = true
		uniqueTo[extractDomain(e.to)] = true
	}
	fmt.Printf("Edges: %d  Source domains: %d  Target domains: %d\n",
		len(edges), len(uniqueFrom), len(uniqueTo))

	if flags.verbose {
		fmt.Println()
		fmt.Println("Adjacency:")
		adj := map[string][]string{}
		for _, e := range edges {
			from := extractDomain(e.from)
			to := extractDomain(e.to)
			adj[from] = append(adj[from], to)
		}
		for from, tos := range adj {
			fmt.Printf("  %s:\n", from)
			for _, to := range tos {
				fmt.Printf("    → %s\n", to)
			}
		}
	}
}

// ── graph status: quick health check ──

func graphStatus() {
	requireCF()

	zones := fetchZones()
	fmt.Printf("Zones: %d\n", len(zones))

	totalRecords := 0
	type zoneSummary struct {
		name    string
		a       int
		cname   int
		txt     int
		mx      int
		other   int
	}
	var summaries []zoneSummary

	for _, z := range zones {
		records := fetchDNS(z.ID)
		totalRecords += len(records)
		s := zoneSummary{name: z.Name}
		for _, r := range records {
			switch r.Type {
			case "A", "AAAA":
				s.a++
			case "CNAME":
				s.cname++
			case "TXT":
				s.txt++
			case "MX":
				s.mx++
			default:
				s.other++
			}
		}
		summaries = append(summaries, s)
	}

	fmt.Printf("Total DNS records: %d\n\n", totalRecords)
	fmt.Println("Zone breakdown:")
	for _, s := range summaries {
		fmt.Printf("  %-20s %2d A/AAAA  %2d CNAME  %2d TXT  %2d MX\n",
			s.name, s.a, s.cname, s.txt, s.mx)
	}
}

// ── Cloudflare API helpers (reuse cfAPI from main.go) ──

type zoneInfo struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type dnsRecord struct {
	Name    string `json:"name"`
	Type    string `json:"type"`
	Content string `json:"content"`
	Proxied bool   `json:"proxied"`
}

func fetchZones() []zoneInfo {
	data, err := cfAPI("/zones?per_page=50")
	if err != nil {
		bail("fetch zones: %v", err)
	}
	var resp struct {
		Result []zoneInfo `json:"result"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		bail("parse zones: %v", err)
	}
	return resp.Result
}

func fetchDNS(zoneID string) []dnsRecord {
	data, err := cfAPI("/zones/" + zoneID + "/dns_records?per_page=100")
	if err != nil {
		return nil
	}
	var resp struct {
		Result []dnsRecord `json:"result"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil
	}
	return resp.Result
}
