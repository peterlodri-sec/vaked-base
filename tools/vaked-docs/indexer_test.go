// Vaked Docs — TF-IDF indexer unit tests.
// GENESIS_SEAL: 7c242080
package main

import (
	"testing"
)

func TestNewIndexer(t *testing.T) {
	ix := NewIndexer()
	if ix == nil {
		t.Fatal("NewIndexer returned nil")
	}
	if ix.Index == nil {
		t.Fatal("NewIndexer has nil Index")
	}
	if ix.Index.NextID != 1 {
		t.Errorf("expected NextID=1, got %d", ix.Index.NextID)
	}
	if ix.Index.DocCount != 0 {
		t.Errorf("expected DocCount=0, got %d", ix.Index.DocCount)
	}
}

func TestAddDocument(t *testing.T) {
	ix := NewIndexer()
	id := ix.AddDocument("test/pkg", "test query", "hello world hello")
	if id != 1 {
		t.Errorf("expected docID=1, got %d", id)
	}

	if ix.Index.DocCount != 1 {
		t.Errorf("expected DocCount=1, got %d", ix.Index.DocCount)
	}

	doc := ix.GetDoc(id)
	if doc == nil {
		t.Fatal("GetDoc returned nil")
	}
	if doc.PackageID != "test/pkg" {
		t.Errorf("expected PackageID=test/pkg, got %s", doc.PackageID)
	}
	if doc.Query != "test query" {
		t.Errorf("expected Query=test query, got %s", doc.Query)
	}
	if doc.DocID != 1 {
		t.Errorf("expected DocID=1, got %d", doc.DocID)
	}
}

func TestInvertedIndex(t *testing.T) {
	ix := NewIndexer()

	// Doc 1: "hello world"
	ix.AddDocument("pkg/a", "q1", "hello world")
	// Doc 2: "hello there"
	ix.AddDocument("pkg/b", "q2", "hello there")

	// "hello" appears in both docs -> df=2
	// "world" appears in doc 1 only -> df=1
	// "there" appears in doc 2 only -> df=1

	terms, totalDocs := ix.IndexSize()
	if totalDocs != 2 {
		t.Errorf("expected 2 docs, got %d", totalDocs)
	}

	// Check postings
	helloPostings := ix.Index.Index["hello"]
	if helloPostings == nil {
		t.Fatal("expected postings for 'hello'")
	}
	if len(helloPostings) != 2 {
		t.Errorf("expected 'hello' in 2 docs, got %d", len(helloPostings))
	}

	worldPostings := ix.Index.Index["world"]
	if worldPostings == nil {
		t.Fatal("expected postings for 'world'")
	}
	if len(worldPostings) != 1 {
		t.Errorf("expected 'world' in 1 doc, got %d", len(worldPostings))
	}

	_ = terms // terms may vary by tokenization
}

func TestIDF(t *testing.T) {
	ix := NewIndexer()
	// Single doc containing "unique"
	ix.AddDocument("pkg", "q", "unique term here")

	idf := ix.IDF("unique")
	if idf <= 0 {
		t.Errorf("expected positive IDF for 'unique', got %f", idf)
	}

	// Term not in index
	idfMissing := ix.IDF("nonexistent")
	if idfMissing != 0 {
		t.Errorf("expected IDF=0 for missing term, got %f", idfMissing)
	}

	// Two docs, both have "common"
	ix.AddDocument("pkg2", "q2", "common word")
	idfCommon := ix.IDF("common")
	if idfCommon <= 0 {
		t.Errorf("expected positive IDF for 'common', got %f", idfCommon)
	}
}

func TestTermFrequency(t *testing.T) {
	ix := NewIndexer()
	id := ix.AddDocument("pkg", "q", "zig zig zig build")
	tf := ix.TermFrequency("zig", id)
	if tf != 3 {
		t.Errorf("expected tf=3 for 'zig', got %d", tf)
	}

	tfMissing := ix.TermFrequency("build", id)
	if tfMissing != 1 {
		t.Errorf("expected tf=1 for 'build', got %d", tfMissing)
	}

	tfNotFound := ix.TermFrequency("nonexistent", id)
	if tfNotFound != 0 {
		t.Errorf("expected tf=0 for missing term, got %d", tfNotFound)
	}
}

func TestAverageDocLength(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg", "q", "short")          // 1 term
	ix.AddDocument("pkg", "q", "medium length")   // 2 terms
	ix.AddDocument("pkg", "q", "longer document here") // 3 terms

	avg := ix.AverageDocLength()
	if avg != 2.0 {
		t.Errorf("expected avg doc length=2.0, got %f", avg)
	}
}

func TestAllDocs(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg", "q1", "doc one")
	ix.AddDocument("pkg", "q2", "doc two")

	allDocs := ix.AllDocs()
	if len(allDocs) != 2 {
		t.Errorf("expected 2 docs, got %d", len(allDocs))
	}

	found := false
	for _, d := range allDocs {
		if d.Query == "q1" && d.PackageID == "pkg" {
			found = true
		}
	}
	if !found {
		t.Error("expected q1/pkg in AllDocs")
	}
}

func TestEmptyIndexer(t *testing.T) {
	ix := NewIndexer()
	if ix.AverageDocLength() != 0 {
		t.Errorf("expected avg=0 for empty index")
	}
	if ix.IDF("anything") != 0 {
		t.Errorf("expected IDF=0 for empty index")
	}
	allDocs := ix.AllDocs()
	if len(allDocs) != 0 {
		t.Errorf("expected 0 docs from empty index")
	}
}
