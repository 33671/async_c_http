#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <curl/curl.h>

/* Load .env file into environment variables */
void load_env_file(const char *path) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return;  /* Silently skip if file doesn't exist */
    }
    
    printf("Loading environment from: %s\n", path);
    char line[1024];
    while (fgets(line, sizeof(line), fp)) {
        /* Remove trailing newline/carriage return */
        size_t len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) {
            line[--len] = '\0';
        }
        
        /* Skip empty lines and comments */
        if (len == 0 || line[0] == '#') continue;
        
        /* Find the '=' separator */
        char *eq = strchr(line, '=');
        if (!eq) continue;
        
        *eq = '\0';
        char *key = line;
        char *value = eq + 1;
        
        /* Trim whitespace from key */
        while (*key == ' ' || *key == '\t') key++;
        char *kend = key + strlen(key) - 1;
        while (kend > key && (*kend == ' ' || *kend == '\t')) *kend-- = '\0';
        
        /* Trim whitespace from value (optional) */
        while (*value == ' ' || *value == '\t') value++;
        
        /* Skip if key is empty */
        if (strlen(key) == 0) continue;
        
        /* Set environment variable, overwriting any existing value */
        setenv(key, value, 1);
    }
    
    fclose(fp);
}