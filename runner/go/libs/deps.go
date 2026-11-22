// Package deps pins the libraries offered to the models for Go (draft
// Section IV-B): net/http (std), resty, go-retryablehttp, cenkalti/backoff.
// Both stable major versions are installed where two exist (resty v2 and the
// v3 release candidate; backoff v4 and v5), so that either import path builds.
package deps

import (
	_ "github.com/cenkalti/backoff/v4"
	_ "github.com/cenkalti/backoff/v5"
	_ "github.com/go-resty/resty/v2"
	_ "github.com/hashicorp/go-retryablehttp"
	_ "resty.dev/v3"
)
