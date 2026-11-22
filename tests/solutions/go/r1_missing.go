package main

import "github.com/sony/gobreaker"

func GetUserProfile(baseURL, userID string) (map[string]any, error) { _ = gobreaker.StateOpen; return nil, nil }
