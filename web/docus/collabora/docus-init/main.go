package main

import (
	"log"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

const (
	flagPath    = "/flag.txt"
	flagTimeout = 60 * time.Second
)

var coolwsdArgs = []string{
	"--use-env-vars",
	"--o:sys_template_path=/opt/cool/systemplate",
	"--o:child_root_path=/opt/cool/child-roots",
	"--o:file_server_root_path=/usr/share/coolwsd",
	"--o:cache_files.path=/opt/cool/cache",
	"--o:logging.color=false",
	"--o:stop_on_config_change=true",
}

func waitFlag() {
	deadline := time.Now().Add(flagTimeout)
	var lastErr error
	for {
		if st, err := os.Stat(flagPath); err == nil && st.Size() > 0 {
			return
		} else {
			lastErr = err
		}
		if time.Now().After(deadline) {
			log.Fatalf("no %s: %v", flagPath, lastErr)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func main() {
	waitFlag()
	log.Printf("flag present at %s", flagPath)

	cmd := exec.Command("/usr/bin/coolwsd", coolwsdArgs...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		log.Fatalf("start coolwsd: %v", err)
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		sig := <-sigCh
		if err := cmd.Process.Signal(sig); err != nil {
			log.Printf("forward signal: %v", err)
		}
	}()

	go func() {
		for {
			var status syscall.WaitStatus
			_, err := syscall.Wait4(-1, &status, syscall.WNOHANG, nil)
			if err != nil {
				time.Sleep(time.Second)
			}
			time.Sleep(200 * time.Millisecond)
		}
	}()

	if err := cmd.Wait(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		log.Fatalf("coolwsd: %v", err)
	}
}
