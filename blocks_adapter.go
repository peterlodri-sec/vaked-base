package tools

import (
	"fmt"
	"os"
	"github.com/usewhale/whale/internal/blocks"
	"path/filepath"
	"strings"
)

// toErr adapts blocks.Write's (*Block, error) to plain error for existing code.
func toErr(_ *blocks.Block, err error) error { return err }
