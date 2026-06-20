// Vaked Docs — crawler unit tests.
// Tests URL parsing, markdown parsing, and rate limit handling.
// No network calls — pure unit tests.
// GENESIS_SEAL: 7c242080
package main

import (
	"strings"
	"testing"
)

func TestParseRepoURL(t *testing.T) {
	tests := []struct {
		raw       string
		wantOwner string
		wantRepo  string
		wantErr   bool
	}{
		{"https://github.com/ziglang/zig", "ziglang", "zig", false},
		{"https://github.com/ziglang/zig.git", "ziglang", "zig", false},
		{"ziglang/zig", "ziglang", "zig", false},
		{"https://github.com/nixos/nixpkgs", "nixos", "nixpkgs", false},
		{"tauri-apps/tauri", "tauri-apps", "tauri", false},
		{"", "", "", true},
		{"invalid", "", "", true},
		{"https://github.com/onlyowner", "", "", true},
	}

	for _, tt := range tests {
		owner, repo, err := ParseRepoURL(tt.raw)
		if tt.wantErr {
			if err == nil {
				t.Errorf("ParseRepoURL(%q) expected error, got %s/%s", tt.raw, owner, repo)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParseRepoURL(%q) unexpected error: %v", tt.raw, err)
			continue
		}
		if owner != tt.wantOwner || repo != tt.wantRepo {
			t.Errorf("ParseRepoURL(%q) = %s/%s, want %s/%s", tt.raw, owner, repo, tt.wantOwner, tt.wantRepo)
		}
	}
}

func TestParseMarkdownHeadings(t *testing.T) {
	content := `# Zig Build System

This is the Zig build system documentation.

## std.Build

The build function receives a *std.Build.

### addExecutable

Creates an executable artifact.

## std.Test

Testing utilities.
`
	entries := parseMarkdown("build.md", content)
	if len(entries) < 3 {
		t.Fatalf("expected at least 3 entries from headings, got %d", len(entries))
	}

	// First entry should be an intro or the first section
	foundBuild := false
	foundTest := false
	for _, e := range entries {
		if e.Query == "std.Build" {
			foundBuild = true
		}
		if e.Query == "std.Test" {
			foundTest = true
		}
	}

	if !foundBuild {
		t.Error("expected entry with Query 'std.Build'")
	}
	if !foundTest {
		t.Error("expected entry with Query 'std.Test'")
	}
}

func TestParseMarkdownCodeBlocks(t *testing.T) {
	content := `# Code Example

Here is a code block:

` + "```zig\nconst std = @import(\"std\");\n```\n" + `

And another:

` + "```\n$ echo hello\n```\n"

	entries := parseMarkdown("code.md", content)
	if len(entries) == 0 {
		t.Fatal("expected at least one entry")
	}

	foundCode := false
	for _, e := range entries {
		for _, s := range e.Snippets {
			if s.Code != "" {
				foundCode = true
				if !contains(s.Code, "const std") && !contains(s.Code, "echo hello") {
					t.Errorf("code snippet doesn't match expected content: %q", s.Code)
				}
			}
		}
	}

	if !foundCode {
		t.Error("expected at least one code snippet in parsed entries")
	}
}

func TestParseMarkdownEmpty(t *testing.T) {
	entries := parseMarkdown("empty.md", "")
	if len(entries) != 0 {
		t.Errorf("expected 0 entries for empty content, got %d", len(entries))
	}

	entries = parseMarkdown("whitespace.md", "   \n\n  \n")
	if len(entries) != 0 {
		t.Errorf("expected 0 entries for whitespace-only content, got %d", len(entries))
	}
}

func TestParseMarkdownNoHeadings(t *testing.T) {
	content := "Just a single paragraph of documentation without any headings whatsoever."
	entries := parseMarkdown("plain.md", content)
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry for content with no headings, got %d", len(entries))
	}
	if entries[0].PackageID == "" {
		t.Error("expected non-empty PackageID")
	}
}

func TestTokenize(t *testing.T) {
	tests := []struct {
		input string
		want  []string
	}{
		{"hello world", []string{"hello", "world"}},
		{"std.Build API", []string{"std.build", "api"}},
		{"ArrayListUnmanaged", []string{"arraylistunmanaged"}},
		{"k1=1.5, b=0.75", []string{"k1", "1.5", "b", "0.75"}},
		{"  leading/trailing  ", []string{"leading", "trailing"}},
	}
	for _, tt := range tests {
		got := Tokenize(tt.input)
		if !stringSliceEqual(got, tt.want) {
			t.Errorf("Tokenize(%q) = %v, want %v", tt.input, got, tt.want)
		}
	}
}

func TestExtractTitle(t *testing.T) {
	content := "# My Document Title\n\nSome content."
	title := extractTitle("file.md", content)
	if title != "My Document Title" {
		t.Errorf("extractTitle = %q, want %q", title, "My Document Title")
	}

	// Fallback to filename
	title2 := extractTitle("readme.md", "")
	if title2 == "" {
		t.Error("expected fallback title from filename")
	}
}

func TestRateLimitError(t *testing.T) {
	err := &RateLimitError{
		StatusCode: 403,
		Remaining:  "0",
		Reset:      "1234567890",
		Body:       "rate limit exceeded",
	}
	msg := err.Error()
	if !contains(msg, "403") || !contains(msg, "0") {
		t.Errorf("RateLimitError.Error() = %q, expected status and remaining", msg)
	}
}

// ── Helpers ───────────────────────────────────────────────────

func contains(s, substr string) bool {
	return strings.Contains(s, substr)
}

func stringSliceEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
