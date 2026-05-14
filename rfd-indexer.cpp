#include <iostream>
#include <filesystem>
#include <fstream>
#include <vector>
#include <string>
#include <unordered_map>
#include <sqlite3.h>
#include <magic.h>

#include <openssl/sha.h>

namespace fs = std::filesystem;

// =========================================================
// CONFIG
// =========================================================

static const std::string SOURCE_ROOT = "/path/to/recovered";
static const std::string DEST_ROOT   = "/path/to/sorted";

// =========================================================
// MAGIC DETECTION
// =========================================================
magic_t magic_cookie;

std::string detect_filetype(const fs::path &file) {

    const char *result = magic_file(magic_cookie, file.c_str());

    if (!result) return "unknown";

    std::string mime(result);

    // libmagic returns like: "image/jpeg; charset=binary"
    size_t semi = mime.find(';');
    if (semi != std::string::npos) {
        mime = mime.substr(0, semi);
    }

    size_t slash = mime.find('/');
    if (slash != std::string::npos) {
        return mime.substr(slash + 1); // jpeg, png, pdf, etc.
    }

    return "unknown";
}

// =========================================================
// SHA256
// =========================================================

std::string sha256_file(const fs::path &file) {
    unsigned char hash[SHA256_DIGEST_LENGTH];

    std::ifstream f(file, std::ios::binary);
    if (!f) return "";

    SHA256_CTX ctx;
    SHA256_Init(&ctx);

    std::vector<char> buffer(1024 * 1024);

    while (f.good()) {
        f.read(buffer.data(), buffer.size());
        SHA256_Update(&ctx, buffer.data(), f.gcount());
    }

    SHA256_Final(hash, &ctx);

    std::string hex;
    hex.reserve(64);

    static const char *digits = "0123456789abcdef";

    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        hex.push_back(digits[(hash[i] >> 4) & 0xF]);
        hex.push_back(digits[hash[i] & 0xF]);
    }

    return hex;
}

// =========================================================
// SQLITE
// =========================================================

sqlite3 *db;

void init_db() {
    fs::create_directories(DEST_ROOT);

    std::string db_path = DEST_ROOT + "/sorting_progress.db";

    sqlite3_open(db_path.c_str(), &db);

    sqlite3_exec(db, "PRAGMA journal_mode=WAL;", nullptr, nullptr, nullptr);

    const char *sql =
        "CREATE TABLE IF NOT EXISTS processed_files ("
        "source_path TEXT PRIMARY KEY,"
        "recup_dir TEXT,"
        "detected_type TEXT,"
        "sha256 TEXT UNIQUE,"
        "filesize INTEGER,"
        "destination_path TEXT,"
        "status TEXT,"
        "processed_at TEXT"
        ");";

    sqlite3_exec(db, sql, nullptr, nullptr, nullptr);

    sqlite3_exec(db,
        "CREATE INDEX IF NOT EXISTS idx_sha256 ON processed_files(sha256);",
        nullptr, nullptr, nullptr);
}

// =========================================================
// DB CHECK
// =========================================================

bool already_seen_hash(const std::string &hash) {
    sqlite3_stmt *stmt;

    const char *sql = "SELECT 1 FROM processed_files WHERE sha256=? LIMIT 1;";

    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
    sqlite3_bind_text(stmt, 1, hash.c_str(), -1, SQLITE_STATIC);

    bool exists = sqlite3_step(stmt) == SQLITE_ROW;

    sqlite3_finalize(stmt);

    return exists;
}

// =========================================================
// INSERT
// =========================================================

void mark_processed(
    const std::string &src,
    const std::string &recup,
    const std::string &type,
    const std::string &hash,
    uintmax_t filesize,
    const std::string &dst,
    const std::string &status
) {
    sqlite3_stmt *stmt;

    const char *sql =
        "INSERT OR REPLACE INTO processed_files "
        "(source_path, recup_dir, detected_type, sha256, filesize, destination_path, status, processed_at) "
        "VALUES (?,?,?,?,?,?,?,datetime('now'));";

    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);

    sqlite3_bind_text(stmt, 1, src.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 2, recup.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, type.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 4, hash.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_int64(stmt, 5, static_cast<sqlite3_int64>(filesize));
    sqlite3_bind_text(stmt, 6, dst.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 7, status.c_str(), -1, SQLITE_STATIC);

    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

// =========================================================
// DEST HELPERS
// =========================================================

fs::path build_dest(const fs::path &dir, const std::string &name) {
    fs::path p = dir / name;

    if (!fs::exists(p)) return p;

    int i = 1;
    fs::path base = p;

    while (fs::exists(p)) {
        p = base.parent_path() /
            (base.stem().string() + "_" + std::to_string(i) + base.extension().string());
        i++;
    }

    return p;
}

// =========================================================
// PROCESS FILE
// =========================================================

void process_file(const fs::path &file, const std::string &recup_dir) {

    std::string src = fs::absolute(file).string();

    std::ifstream f(file, std::ios::binary);
    if (!f) return;

    char header_buf[64] = {0};
    f.read(header_buf, sizeof(header_buf));

    std::string header(header_buf, f.gcount());

    std::string type = detect_filetype(header);
    uintmax_t filesize = fs::file_size(file);
    std::string hash = sha256_file(file);

    if (hash.empty()) return;

    if (already_seen_hash(hash)) {
        // duplicate detected (optional skip logic)
        return;
    }

    fs::path dest_dir = fs::path(DEST_ROOT) / type / recup_dir;
    fs::create_directories(dest_dir);

    fs::path dest = build_dest(dest_dir, file.filename().string());

    try {
        fs::rename(file, dest);
        mark_processed(src, recup_dir, type, hash, filesize, dest.string(), "success");
    }
    catch (...) {
        mark_processed(src, recup_dir, type, hash, filesize, dest.string(), "error");
    }
}

// =========================================================
// MAIN
// =========================================================

int main() {
    init_db();

    magic_cookie = magic_open(MAGIC_MIME_TYPE);

    if (!magic_cookie) {
        std::cerr << "Failed to initialize libmagic\n";
        exit(1);
    }

    if (magic_load(magic_cookie, nullptr) != 0) {
        std::cerr << "libmagic load error: " << magic_error(magic_cookie) << "\n";
        exit(1);
    }

    std::vector<fs::path> recups;

    for (auto &p : fs::directory_iterator(SOURCE_ROOT)) {
        if (p.is_directory() &&
            p.path().filename().string().find("recup_dir.") == 0) {
            recups.push_back(p.path());
        }
    }

    std::sort(recups.begin(), recups.end());

    int idx = 1;

    for (auto &dir : recups) {

        std::cout << "[" << idx++ << "/" << recups.size()
                  << "] " << dir.filename() << "\n";

        int count = 0;

        for (auto &file : fs::directory_iterator(dir)) {
            if (!file.is_regular_file()) continue;

            process_file(file.path(), dir.filename().string());

            if (++count % 100 == 0) {
                std::cout << "  processed " << count << " files\n";
            }
        }
    }

    sqlite3_close(db);

    std::cout << "Done.\n";
    return 0;
}