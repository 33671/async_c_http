#include <stdio.h>
#include <string.h>
#include "lw_terminal_vt100.h"

static void print_screen(struct lw_terminal_vt100 *vt, const char *label)
{
    const char **lines = lw_terminal_vt100_getlines(vt);
    printf("=== %s (%ux%u) ===\n", label, vt->width, vt->height);
    for (unsigned int y = 0; y < vt->height; y++) {
        printf("|%.*s|\n", vt->width, lines[y]);
    }
    printf("\n");
}

int main()
{
    /* --- Default 80x24 --- */
    struct lw_terminal_vt100 *vt = lw_terminal_vt100_init(NULL, NULL);
    lw_terminal_vt100_read_str(vt, "\033[2J");            /* clear */
    lw_terminal_vt100_read_str(vt, "Hello world!\n");
    lw_terminal_vt100_read_str(vt, "\033[31mRed text\033[0m\n");
    lw_terminal_vt100_read_str(vt, "\033[7mInverse\033[0m\n");
    print_screen(vt, "default 80x24");
    lw_terminal_vt100_destroy(vt);

    /* --- Custom 40x10 --- */
    struct lw_terminal_vt100 *vt2 = lw_terminal_vt100_init2(NULL, 40, 10, NULL);
    lw_terminal_vt100_read_str(vt2, "\033[2J");
    lw_terminal_vt100_read_str(vt2, "Line 1\nLine 2\nLine 3\n");
    lw_terminal_vt100_read_str(vt2, "\033[5;5HPositioned text");
    print_screen(vt2, "custom 40x10");
    lw_terminal_vt100_destroy(vt2);

    return 0;
}
