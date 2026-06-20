// Vaked Docs — shared helpers.
// GENESIS_SEAL: 7c242080
package main

import (
	"strings"
	"unicode"
)

// ── Tokenizer ─────────────────────────────────────────────────

// TokenizeAll splits text into lowercase alphanumeric tokens.
// Handles hyphens, underscores, and dots within tokens.
// This is the canonical tokenizer used by the indexer and search.
func TokenizeAll(text string) []string {
	var tokens []string
	var current strings.Builder
	lower := strings.ToLower(text)

	for _, r := range lower {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' || r == '-' || r == '.' {
			current.WriteRune(r)
		} else {
			if current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			}
		}
	}
	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}
	return tokens
}

// ── Document content assembly ─────────────────────────────────

// assembleContent combines a DocSnippet's Code and Content fields into a
// single searchable text string.
func assembleContent(s DocSnippet) string {
	if s.Code == "" {
		return s.Content
	}
	if s.Content == "" {
		return s.Code
	}
	return s.Code + "\n" + s.Content
}

// ── Title case (replacement for deprecated strings.Title) ─────

// toTitle converts a word to title case (first rune uppercase, rest lowercase).
func toTitle(s string) string {
	if s == "" {
		return ""
	}
	runes := []rune(s)
	first := unicode.ToUpper(runes[0])
	if len(runes) == 1 {
		return string(first)
	}
	var rest strings.Builder
	for _, r := range runes[1:] {
		rest.WriteRune(unicode.ToLower(r))
	}
	return string(first) + rest.String()
}

// wordToTitle converts each space-separated word to title case.
func wordsToTitle(s string) string {
	fields := strings.Fields(s)
	for i, f := range fields {
		fields[i] = toTitle(f)
	}
	return strings.Join(fields, " ")
}
