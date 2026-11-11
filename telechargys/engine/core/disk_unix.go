//go:build !windows

package core

import "syscall"

// diskFree : octets libres sur le disque qui contient dir (-1 si inconnu).
func diskFree(dir string) int64 {
	var st syscall.Statfs_t
	if err := syscall.Statfs(dir, &st); err != nil {
		return -1
	}
	return int64(st.Bavail) * int64(st.Bsize)
}
