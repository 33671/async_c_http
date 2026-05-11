/*
 * diff.h
 *
 * Public API for unified-diff generation based on Harold Stone's algorithm.
 * Adapted from busybox diff for library use.
 */

#ifndef DIFF_H
#define DIFF_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Generate a unified diff between two text buffers.
 *
 * Returns a malloc'd diff string on success, or NULL if the inputs
 * are identical or on error.  The caller must free the result.
 *
 * Parameters:
 *   old_text, old_len – original content
 *   new_text, new_len – modified content
 *   context_lines      – number of context lines (typically 3)
 */
char *diff_text(const char *old_text, size_t old_len,
                const char *new_text, size_t new_len,
                int context_lines);

#ifdef __cplusplus
}
#endif

#endif /* DIFF_H */
