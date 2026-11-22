// resty v2 + context parameter + struct pointer return (glue tolerance check).
package main

import (
	"context"
	"github.com/go-resty/resty/v2"
	_ "github.com/cenkalti/backoff/v4"
	_ "github.com/cenkalti/backoff/v5"
	_ "github.com/hashicorp/go-retryablehttp"
	_ "resty.dev/v3"
)

type UserProfile struct {
	ID    string `json:"id"`
	Email string `json:"email"`
}

func GetUserProfile(ctx context.Context, baseURL, userID string) (*UserProfile, error) {
	var u UserProfile
	_, err := resty.New().R().SetContext(ctx).SetResult(&u).Get(baseURL + "/v1/users/" + userID)
	return &u, err
}
