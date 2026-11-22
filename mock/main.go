// Command mock is the fault-injecting stand-in for every dependency of the
// benchmark tasks (draft Section IV-C).
package main

import (
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"
)

var version = "dev" // set with -ldflags "-X main.version=..."

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}

func ifaceForIP(ip string) (string, error) {
	ifs, err := net.Interfaces()
	if err != nil {
		return "", err
	}
	for _, i := range ifs {
		addrs, _ := i.Addrs()
		for _, a := range addrs {
			if n, ok := a.(*net.IPNet); ok && n.IP.String() == ip {
				return i.Name, nil
			}
		}
	}
	return "", fmt.Errorf("no interface with address %s", ip)
}

func binaryHash() string {
	p, err := os.Executable()
	if err != nil {
		return ""
	}
	f, err := os.Open(p)
	if err != nil {
		return ""
	}
	defer f.Close()
	h := sha256.New()
	io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil))
}

func loadTLS(cert, key string) (*tls.Config, error) {
	c, err := tls.LoadX509KeyPair(cert, key)
	if err != nil {
		return nil, err
	}
	return &tls.Config{
		Certificates: []tls.Certificate{c},
		NextProtos:   []string{"http/1.1"}, // ALPN: HTTP/1.1 only
		MinVersion:   tls.VersionTLS12,
	}, nil
}

func (s *Server) controlMux() *http.ServeMux {
	mux := http.NewServeMux()
	reply := func(w http.ResponseWriter, code int, v any) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		json.NewEncoder(w).Encode(v)
	}
	mux.HandleFunc("GET /v1/health", func(w http.ResponseWriter, _ *http.Request) {
		reply(w, 200, map[string]any{"ok": true, "version": s.version, "binary_sha256": binaryHash(),
			"tasks": taskIDs(), "ports": portTable, "capture_iface": s.capIface, "active_run": s.current() != nil})
	})
	mux.HandleFunc("GET /v1/clock", func(w http.ResponseWriter, _ *http.Request) {
		reply(w, 200, sampleClockPair())
	})
	mux.HandleFunc("POST /v1/run/start", func(w http.ResponseWriter, req *http.Request) {
		var cfg RunConfig
		dec := json.NewDecoder(req.Body)
		dec.DisallowUnknownFields()
		if err := dec.Decode(&cfg); err != nil {
			reply(w, 400, map[string]string{"error": err.Error()})
			return
		}
		r, err := s.startRun(cfg)
		if err != nil {
			reply(w, 409, map[string]string{"error": err.Error()})
			return
		}
		reply(w, 200, map[string]any{"ok": true, "config": r.Cfg, "start_clock": r.StartPair, "fault_firewall_rules": r.fwRules,
			"capture": r.capture != nil})
	})
	mux.HandleFunc("POST /v1/run/finish", func(w http.ResponseWriter, _ *http.Request) {
		sum, err := s.finishRun()
		if err != nil {
			reply(w, 409, map[string]string{"error": err.Error()})
			return
		}
		reply(w, 200, sum)
	})
	return mux
}

func (s *Server) listenDeps(bindIP string) error {
	for _, p := range portTable {
		ln, err := net.Listen("tcp4", net.JoinHostPort(bindIP, strconv.Itoa(p.Port)))
		if err != nil {
			return err
		}
		go s.serve(ln, p)
	}
	return nil
}

func main() {
	var (
		dataRoot = flag.String("data", "/data", "root directory for run logs")
		intIP    = flag.String("int-ip", "", "mock address on the solution network (dependency ports bind here; capture iface is found by it)")
		ctlAddr  = flag.String("ctl", "", "control API address (ip:port) on the control network")
		certF    = flag.String("cert", "/certs/mock.pem", "server certificate (PEM)")
		keyF     = flag.String("key", "/certs/mock-key.pem", "server key (PEM)")
		noFW     = flag.Bool("no-firewall", false, "disable nftables (unit tests only)")
		noCap    = flag.Bool("no-capture", false, "disable packet capture (unit tests only)")
	)
	flag.Parse()
	tlsCfg, err := loadTLS(*certF, *keyF)
	if err != nil {
		log.Fatalf("tls: %v", err)
	}
	s := &Server{dataRoot: *dataRoot, tlsCfg: tlsCfg, version: version, started: monoNS()}
	iface, err := ifaceForIP(*intIP)
	if err != nil {
		log.Fatalf("int-ip: %v", err)
	}
	_, ctlPortS, err := net.SplitHostPort(*ctlAddr)
	if err != nil {
		log.Fatalf("ctl: %v", err)
	}
	ctlPort, _ := strconv.Atoi(ctlPortS)
	if *noFW {
		s.fw = noFirewall{}
	} else {
		s.fw = nftFirewall{}
	}
	if err := s.fw.setup(iface, ctlPort); err != nil {
		log.Fatalf("firewall: %v", err)
	}
	if !*noCap {
		s.capIface = iface
	}
	if err := s.listenDeps(*intIP); err != nil {
		log.Fatalf("listen: %v", err)
	}
	srv := &http.Server{Addr: *ctlAddr, Handler: s.controlMux(), ReadHeaderTimeout: 10 * time.Second}
	log.Printf("mock %s: deps on %s (iface %s), control on %s", version, *intIP, iface, *ctlAddr)
	log.Fatal(srv.ListenAndServe())
}
