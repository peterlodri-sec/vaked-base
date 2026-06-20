// Vaked Docs — BM25 search ranking.
// Pure Go. No external dependencies.
// GENESIS_SEAL: 7c242080
package main

import (
	"sort"
	"strings"
)

// ── BM25 Scorer ───────────────────────────────────────────────

// BM25Scorer implements the BM25 ranking function.
type BM25Scorer struct {
	Indexer      *TFIDFIndexer
	K1           float64
	B            float64
	AvgDocLength float64
}

// NewBM25Scorer creates a BM25 scorer with standard parameters (k1=1.5, b=0.75).
func NewBM25Scorer(ix *TFIDFIndexer) *BM25Scorer {
	return &BM25Scorer{
		Indexer:      ix,
		K1:           1.5,
		B:            0.75,
		AvgDocLength: ix.AverageDocLength(),
	}
}

// Score computes the BM25 score for a set of query terms against a document.
// BM25 formula: Σ IDF(q) * (tf * (k1+1)) / (tf + k1 * (1 - b + b * |D|/avgdl))
func (s *BM25Scorer) Score(queryTerms []string, docID int) float64 {
	doc := s.Indexer.GetDoc(docID)
	if doc == nil || doc.Length == 0 {
		return 0
	}

	var score float64
	docLen := float64(doc.Length)
	avgdl := s.AvgDocLength
	if avgdl == 0 {
		avgdl = 1
	}

	for _, term := range queryTerms {
		idf := s.Indexer.IDF(term)
		if idf == 0 {
			continue
		}
		tf := float64(s.Indexer.TermFrequency(term, docID))
		if tf == 0 {
			continue
		}

		numer := tf * (s.K1 + 1)
		denom := tf + s.K1*(1-s.B+s.B*docLen/avgdl)
		score += idf * numer / denom
	}

	return score
}

// RankResult represents a single search hit with its BM25 score.
type RankResult struct {
	PackageID string  `json:"package_id"`
	Query     string  `json:"query"`
	Score     float64 `json:"score"`
	DocID     int     `json:"doc_id"`
}

// Search runs BM25 ranking over all indexed documents and returns top-k results.
func (s *BM25Scorer) Search(query string, topK int) []RankResult {
	queryTerms := TokenizeAll(query)
	if len(queryTerms) == 0 {
		return nil
	}

	// Deduplicate query terms
	seen := make(map[string]bool)
	var uniqueTerms []string
	for _, t := range queryTerms {
		if !seen[t] {
			seen[t] = true
			uniqueTerms = append(uniqueTerms, t)
		}
	}

	allDocs := s.Indexer.AllDocs()
	type scored struct {
		doc   *DocRef
		score float64
	}

	var results []scored
	for _, doc := range allDocs {
		score := s.Score(uniqueTerms, doc.DocID)
		if score > 0 {
			results = append(results, scored{doc: doc, score: score})
		}
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].score > results[j].score
	})

	if topK <= 0 || topK > len(results) {
		topK = len(results)
	}

	ranked := make([]RankResult, topK)
	for i := 0; i < topK; i++ {
		ranked[i] = RankResult{
			PackageID: results[i].doc.PackageID,
			Query:     results[i].doc.Query,
			Score:     results[i].score,
			DocID:     results[i].doc.DocID,
		}
	}

	return ranked
}

// ── Tokenizer (shared) ────────────────────────────────────────

// TokenizeAll splits text into lowercase alphanumeric tokens.
// Handles hyphens, underscores, and dots within tokens.
func TokenizeAll(text string) []string {
	var tokens []string
	var current strings.Builder
	lower := strings.ToLower(text)

	for _, r := range lower {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '_' || r == '-' || r == '.' {
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
