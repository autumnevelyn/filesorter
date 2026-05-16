#include <iostream>
#include <filesystem>
#include <fstream>
#include <vector>
#include <string>
#include <unordered_map>
#include <sqlite3.h>
#include <magic.h>
#include <algorithm>
#include <sstream>

#include <openssl/sha.h>

namespace fs = std::filesystem;

// CONFIG
#define DBG
std::unordered_map<std::string, std::string> config;

void load_config(const std::string &path) {
    std::ifstream file(path);
    std::string line;

    while (std::getline(file, line)) {

        // skip comments / empty lines
        if (line.empty() || line[0] == '#')
            continue;

        auto pos = line.find('=');
        if (pos == std::string::npos)
            continue;

        std::string key = line.substr(0, pos);
        std::string value = line.substr(pos + 1);

        config[key] = value;
    }
}

// HELPERS

fs::path build_unique_dest_path(const fs::path &dir, const std::string &name) {
    fs::path p = dir / name;

    if (!fs::exists(p)) return p;

    // create unique filename - append incremental index
    int i = 1;
    fs::path base = p;
    while (fs::exists(p)) {
        p = base.parent_path() /
            (base.stem().string() + "_" + std::to_string(i) + base.extension().string());
        i++;
    }
    return p;
}

void logd(std::string message, auto variable){
#ifdef DBG
    std::cout << "[DEBUG]    " << message << variable << std::endl;
#endif
}

// MAGIC DETECTION
magic_t magic_cookie;
std::string detect_filetype(const fs::path &file) {
    const char *result = magic_file(magic_cookie, file.c_str());
    logd("mime type: ",  result);

    if (!result) return "unknown";

    std::string mime(result);// libmagic returns like: "image/jpeg; charset=binary"

    size_t semi = mime.find(';');
    if (semi != std::string::npos) {
        mime = mime.substr(0, semi);
    }

    size_t slash = mime.find('/');
    if (slash != std::string::npos) {
        return mime.substr(slash + 1); // separated filetype
    }

    return "unknown";
}

// HASHING
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

// DB
sqlite3 *db;

void init_db() {
    fs::create_directories(config["DEST_ROOT"]);

    fs::path db_path = fs::path(config["DEST_ROOT"]) / config["DB_NAME"];

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
    sqlite3_exec(db, "CREATE INDEX IF NOT EXISTS idx_sha256 ON processed_files(sha256);",
        nullptr, nullptr, nullptr);
}

void bindTextOrNull(sqlite3_stmt* stmt,
                    int index,
                    const std::string& value)
{
    if (value.empty() || value == "unknown")
    {
        sqlite3_bind_null(stmt, index);
    }
    else
    {
        sqlite3_bind_text(
            stmt,
            index,
            value.c_str(),
            -1,
            SQLITE_TRANSIENT
        );
    }
}

bool insert(
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

    bindTextOrNull(stmt, 1, src.c_str());
    bindTextOrNull(stmt, 2, recup.c_str());
    bindTextOrNull(stmt, 3, type.c_str());
    bindTextOrNull(stmt, 4, hash.c_str());
    sqlite3_bind_int64(stmt, 5, static_cast<sqlite3_int64>(filesize));
    bindTextOrNull(stmt, 6, dst.c_str());
    bindTextOrNull(stmt, 7, status.c_str());

    int rc = sqlite3_step(stmt);

    if (rc == SQLITE_CONSTRAINT) {
        sqlite3_finalize(stmt);
        return false;
    }

    sqlite3_finalize(stmt);
    return true;
}

void update_status(const std::string &src, const std::string &status) {
    sqlite3_stmt *stmt;

    const char *sql =
        "UPDATE processed_files SET status=? WHERE src=?;";

    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);

    sqlite3_bind_text(stmt, 1, status.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, src.c_str(), -1, SQLITE_TRANSIENT);

    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

// PROCESS FILE
void process_file(const fs::path &file, const std::string &recup_dir) {

    std::string src = fs::absolute(file).string();
    logd("src: ",  src);

    uintmax_t filesize = fs::file_size(file);
    logd("filesize: ",  filesize);
    if (filesize <= 0){
        std::cout << "Empty file, skipped: " << file << std::endl;
        fs::remove(file);
        return;
    }

    // read filetype
    std::string type = detect_filetype(file);
    logd("type: ",  type);

    std::string hash = sha256_file(file);
    logd("hash: ",  hash);

    fs::path dest_dir = fs::path(config["DEST_ROOT"]) / type / recup_dir;
    fs::path path = build_unique_dest_path(dest_dir, file.filename().string());
    logd("path: ",  path);

    // try insert, reserve in DB
    bool inserted = insert(src, recup_dir, type, hash, filesize, path.string(), "pending");

    // duplicate content
    if (!inserted) {
        std::cout << "Duplicate: " << file << std::endl;
        fs::remove(file);

        return;
    }

    try {
        fs::create_directories(dest_dir);
        fs::rename(file, path);
        update_status(src, "success");
    }
    catch (...) {
        update_status(src, "error");
    }
}

// MAIN
int main() {
    load_config(".config");
    init_db();

    magic_cookie = magic_open(MAGIC_MIME_TYPE);

    if (!magic_cookie) {
        std::cerr << "Failed to initialize libmagic\n";
        exit(1);
    }

    if (magic_load(magic_cookie, nullptr) != 0) {
        std::cerr << "libmagic load error: " << magic_error(magic_cookie) << std::endl;
        exit(1);
    }

    std::vector<fs::path> recups;

    for (auto &p : fs::directory_iterator(config["SOURCE_ROOT"])) {
        if (p.is_directory() &&
            p.path().filename().string().find("recup_dir.") == 0) {
            recups.push_back(p.path());
        }
    }
    std::sort(recups.begin(), recups.end());

    int idx = 1;
    for (auto &dir : recups) {
        std::cout << "[" << idx++ << "/" << recups.size()
                  << "] " << dir.filename() << std::endl;

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
