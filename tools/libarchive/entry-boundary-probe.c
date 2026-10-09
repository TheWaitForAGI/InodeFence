/* Benign public-API probe for libarchive write-disk entry boundaries. */

#include <archive.h>
#include <archive_entry.h>

#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void fail_archive(const char *operation, struct archive *archive) {
    const char *detail = archive_error_string(archive);
    fprintf(stderr, "ERROR\t%s\t%s\n", operation, detail == NULL ? "unknown" : detail);
    exit(1);
}

static void require_ok(const char *operation, struct archive *archive, int status) {
    if (status != ARCHIVE_OK) {
        fail_archive(operation, archive);
    }
}

static void copy_entry_data(struct archive *reader, struct archive *writer) {
    const void *buffer;
    size_t size;
    la_int64_t offset;

    for (;;) {
        int status = archive_read_data_block(reader, &buffer, &size, &offset);
        if (status == ARCHIVE_EOF) {
            return;
        }
        require_ok("archive_read_data_block", reader, status);
        status = (int)archive_write_data_block(writer, buffer, size, offset);
        require_ok("archive_write_data_block", writer, status);
    }
}

int main(int argc, char **argv) {
    if (argc < 3 || argc > 4) {
        fprintf(stderr, "usage: %s ARCHIVE DESTINATION [quiet]\n", argv[0]);
        return 2;
    }
    bool quiet = argc == 4 && strcmp(argv[3], "quiet") == 0;
    if (argc == 4 && !quiet) {
        fprintf(stderr, "mode must be quiet when supplied\n");
        return 2;
    }
    if (chdir(argv[2]) != 0) {
        fprintf(stderr, "chdir failed: %s\n", strerror(errno));
        return 1;
    }

    struct archive *reader = archive_read_new();
    struct archive *writer = archive_write_disk_new();
    if (reader == NULL || writer == NULL) {
        fprintf(stderr, "archive allocation failed\n");
        return 1;
    }

    require_ok("archive_read_support_filter_none", reader,
               archive_read_support_filter_none(reader));
    require_ok("archive_read_support_format_tar", reader,
               archive_read_support_format_tar(reader));
    require_ok("archive_write_disk_set_options", writer,
               archive_write_disk_set_options(
                   writer, ARCHIVE_EXTRACT_TIME | ARCHIVE_EXTRACT_PERM |
                               ARCHIVE_EXTRACT_UNLINK | ARCHIVE_EXTRACT_SECURE_NODOTDOT |
                               ARCHIVE_EXTRACT_SECURE_SYMLINKS));
    require_ok("archive_read_open_filename", reader,
               archive_read_open_filename(reader, argv[1], 10240));

    if (!quiet) {
        fprintf(stderr, "LIBARCHIVE\t%s\t%d\n", archive_version_string(),
                ARCHIVE_VERSION_NUMBER);
        fflush(stderr);
    }

    size_t ordinal = 0;
    for (;;) {
        struct archive_entry *entry = NULL;
        int status = archive_read_next_header(reader, &entry);
        if (status == ARCHIVE_EOF) {
            break;
        }
        require_ok("archive_read_next_header", reader, status);
        const char *path = archive_entry_pathname(entry);
        if (path == NULL || strchr(path, '\t') != NULL || strchr(path, '\n') != NULL) {
            fprintf(stderr, "unsupported qualification path\n");
            return 1;
        }

        require_ok("archive_write_header", writer, archive_write_header(writer, entry));
        copy_entry_data(reader, writer);
        require_ok("archive_write_finish_entry", writer,
                   archive_write_finish_entry(writer));
        if (!quiet) {
            fprintf(stderr, "BOUNDARY\t%zu\t%s\n", ordinal, path);
            fflush(stderr);
        }
        ++ordinal;
    }

    require_ok("archive_read_close", reader, archive_read_close(reader));
    if (!quiet) {
        fprintf(stderr, "BEFORE_CLOSE\t%zu\n", ordinal);
        fflush(stderr);
    }
    require_ok("archive_write_close", writer, archive_write_close(writer));
    if (!quiet) {
        fprintf(stderr, "AFTER_CLOSE\t%zu\n", ordinal);
        fflush(stderr);
    }
    require_ok("archive_read_free", reader, archive_read_free(reader));
    require_ok("archive_write_free", writer, archive_write_free(writer));
    return 0;
}
