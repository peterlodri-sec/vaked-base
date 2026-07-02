// Vaked Docs — TF-IDF inverted index.
// No external dependencies. Pure Go standard library.
// GENESIS_SEAL: 7c242080
package main

import (
	"math"
	"sync"
)

// ── Index types ───────────────────────────────────────────────

// DocRef identifies a document in the index.
type DocRef struct {
	PackageID string
	Query     string // the "title" / query label
	DocID     int    // unique numeric ID
	Length    int    // total terms in the document
}

// InvertedIndex maps term → (docID → term frequency in that doc).
type InvertedIndex struct {
	mu       sync.RWMutex
	Index    map[string]map[int]int // term -> docID -> tf
	Docs     map[int]*DocRef       // docID -> doc metadata
	NextID   int                   // next unique doc ID
	DocCount int                   // total documents indexed
}

// TFIDFIndexer builds and queries a TF-IDF inverted index.
type TFIDFIndexer struct {
	Index *InvertedIndex
}

// NewIndexer creates a new TF-IDF indexer.
func NewIndexer() *TFIDFIndexer {
	return &TFIDFIndexer{
		Index: &InvertedIndex{
			Index:  make(map[string]map[int]int),
			Docs:   make(map[int]*DocRef),
			NextID: 1,
		},
	}
}

// AddDocument tokenizes a document and adds it to the index.
// Returns the assigned DocID.
func (ix *TFIDFIndexer) AddDocument(packageID, query string, content string) int {
	ix.Index.mu.Lock()
	defer ix.Index.mu.Unlock()

	tokens := TokenizeAll(content)
	id := ix.Index.NextID

	ix.Index.Docs[id] = &DocRef{
		PackageID: packageID,
		Query:     query,
		DocID:     id,
		Length:    len(tokens),
	}
	ix.Index.NextID++
	ix.Index.DocCount++

	// Count term frequencies for this document
	tf := make(map[string]int)
	for _, t := range tokens {
		tf[t]++
	}

	// Add to inverted index
	for term, freq := range tf {
		if _, ok := ix.Index.Index[term]; !ok {
			ix.Index.Index[term] = make(map[int]int)
		}
		ix.Index.Index[term][id] = freq
	}

	return id
}

// IDF returns the inverse document frequency for a term.
func (ix *TFIDFIndexer) IDF(term string) float64 {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()

	df := len(ix.Index.Index[term])
	if df == 0 {
		return 0
	}
	N := ix.Index.DocCount
	if N == 0 {
		return 0
	}
	return math.Log(1 + (float64(N)-float64(df)+0.5)/(float64(df)+0.5))
}

// TermFrequency returns the frequency of a term in a specific document.
func (ix *TFIDFIndexer) TermFrequency(term string, docID int) int {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()

	if postings, ok := ix.Index.Index[term]; ok {
		return postings[docID]
	}
	return 0
}

// AverageDocLength returns the mean document length across all indexed docs.
func (ix *TFIDFIndexer) AverageDocLength() float64 {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()

	if ix.Index.DocCount == 0 {
		return 0
	}
	var total int
	for _, d := range ix.Index.Docs {
		total += d.Length
	}
	return float64(total) / float64(ix.Index.DocCount)
}

// GetDoc returns the document reference for a given docID.
func (ix *TFIDFIndexer) GetDoc(docID int) *DocRef {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()
	return ix.Index.Docs[docID]
}

// AllDocs returns a copy of all document references.
func (ix *TFIDFIndexer) AllDocs() []*DocRef {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()

	docs := make([]*DocRef, 0, len(ix.Index.Docs))
	for _, d := range ix.Index.Docs {
		docs = append(docs, d)
	}
	return docs
}

// IndexSize returns the number of unique terms and documents.
func (ix *TFIDFIndexer) IndexSize() (terms int, docs int) {
	ix.Index.mu.RLock()
	defer ix.Index.mu.RUnlock()
	return len(ix.Index.Index), ix.Index.DocCount
}


