#!/bin/sh
# Manual (by-hand) checks of each scenario with curl, openssl s_client and
# tcpdump, from a probe container on the solution network of slot 0.
# Usage: tests/integration/e0_manual.sh > data/dev/e0/manual-<stamp>.txt
set -u
K=0
MOCK=10.77.$K.2
CTL=http://127.0.0.1:$((19000 + K))
STAMP=$(date -u +%Y%m%dT%H%M%S)
probe() { docker run --rm --network lcr-int-$K --ip 10.77.$K.3 --cap-drop ALL --read-only --user 65534:65534 lcr-probe:dev sh -c "$1" 2>&1; }
start() { curl -sS -X POST "$CTL/v1/run/start" -d "{\"run_id\":\"manual-$1-$STAMP\",\"task\":\"R1\",\"scenario\":\"$1\",\"out_dir\":\"dev/e0/manual-$STAMP/$1\"}" >/dev/null; }
finish() { curl -sS -X POST "$CTL/v1/run/finish" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("   mock: counts=%s capture=%s errors=%s" % (d["counts"], (d.get("capture") or {}).get("packets_dropped_by_kernel"), d.get("errors")))'; }
pcap() { docker exec lcr-mock-$K tcpdump -r "/data/dev/e0/manual-$STAMP/$1/capture.pcap" -n -ttt 2>/dev/null | head -${2:-20}; }

echo "### S0: openssl s_client offering h2,http/1.1 (ALPN must be http/1.1) and curl"
start S0
probe "echo | openssl s_client -connect $MOCK:9001 -CAfile /ca.pem -alpn h2,http/1.1 -brief 2>&1 | head -8;
       curl -sS --cacert /ca.pem -i https://$MOCK:9001/v1/users/u-001 -w '\ntime_total=%{time_total}\n'"
finish

echo; echo "### S1: curl --connect-timeout 5 (SYNs dropped by nftables in the mock)"
start S1
probe "curl -sS --cacert /ca.pem --connect-timeout 5 https://$MOCK:9001/v1/users/u-001 -w 'time=%{time_total}\n'; echo rc=\$?"
finish; echo "   tcpdump (-ttt = delta between packets):"; pcap S1

echo; echo "### S2: openssl s_client (TCP connects, no ServerHello), 5 s"
start S2
probe "timeout 5 openssl s_client -connect $MOCK:9001 -CAfile /ca.pem </dev/null 2>&1 | head -5; echo rc=\$?"
finish; echo "   tcpdump:"; pcap S2

echo; echo "### S3: curl -v --max-time 5 (request sent, nothing comes back)"
start S3
probe "curl -sS -v --cacert /ca.pem --max-time 5 https://$MOCK:9001/v1/users/u-001 2>&1 | grep -E '^(> GET|< |curl:|\\* (Connected|SSL connection|ALPN))'; echo"
finish

echo; echo "### S4: curl --max-time 9 (headers at once, then 1 byte / 2 s)"
start S4
probe "curl -sS -i --cacert /ca.pem --max-time 9 https://$MOCK:9001/v1/users/u-001 -w '\ntime=%{time_total} size=%{size_download}\n' | tr -s ' '"
finish; echo "   tcpdump, server->client segments (delta times):"
docker exec lcr-mock-$K tcpdump -r "/data/dev/e0/manual-$STAMP/S4/capture.pcap" -n -ttt 'src port 9001 and greater 60' 2>/dev/null | head -12

for sc in S5a S5b S6a S6b; do
  echo; echo "### $sc: three attempts with curl -i"
  start $sc
  probe "for i in 1 2 3; do curl -sS -i --cacert /ca.pem https://$MOCK:9001/v1/users/u-001 | grep -E '^(HTTP|Date|Retry-After)'; done"
  finish
done

echo; echo "### S7: requests over 32 s (503 for 30 s from first connection, then 200)"
start S7
probe "for i in \$(seq 1 9); do printf '%s ' \$(date +%s); curl -sS -o /dev/null -w '%{http_code}\n' --cacert /ca.pem https://$MOCK:9001/v1/users/u-00\$i; sleep 3.7; done"
finish

echo; echo "### S8: curl -v (connection reset after the request was processed)"
start S8
probe "curl -sS -v --cacert /ca.pem https://$MOCK:9001/v1/users/u-001 2>&1 | grep -E '^(> GET|< |curl:)'"
finish; echo "   tcpdump (RST from server):"; pcap S8 30 | grep -E 'Flags \[R' | head -3

echo; echo "### S9: curl (RST to SYN)"
start S9
probe "curl -sS --cacert /ca.pem https://$MOCK:9001/v1/users/u-001 -w 'time=%{time_total}\n'; echo rc=\$?"
finish; echo "   tcpdump:"; pcap S9
