# Disk Space Solutions for Large Datasets

## Problem

The FNSPID dataset file (`nasdaq_exteral_data.csv`) is **23.2 GB**. When the download script tries to copy it, you need:
- 23.2 GB for the cached file
- 23.2 GB for the copied file
- **Total: ~46 GB** of free disk space

This causes `[WinError 112] There is not enough space on the disk`.

## Solution: Use Cached File Directly

The download script now **automatically detects large files** and uses the cached file directly instead of copying. This saves 23.2 GB of disk space.

### How It Works

1. **Download to cache** (Hugging Face cache folder)
2. **Create marker file** (`fnspid_nasdaq_news_cache_path.txt`) with cache location
3. **Skip copying** (saves 23.2 GB)
4. **Processing script** reads directly from cache

### Cache Location

Default Hugging Face cache location:
```
C:\Users\<username>\.cache\huggingface\hub\datasets--Zihan1004--FNSPID\...
```

## Option 1: Use Cache Directly (Recommended)

**Already implemented!** The scripts now:
- ✅ Detect large files (>10GB)
- ✅ Use cached file directly
- ✅ Process in chunks to avoid RAM issues
- ✅ Save disk space

**Just run:**
```bash
python scripts/download_fnspid.py  # Downloads to cache (no copy)
python scripts/process_fnspid.py    # Reads from cache directly
```

## Option 2: Move Cache to Different Drive

If your C: drive is full, move the Hugging Face cache to a drive with more space:

### Windows Environment Variable

1. Open **System Properties** → **Environment Variables**
2. Add new variable:
   - **Variable Name:** `HF_HOME`
   - **Variable Value:** `D:\huggingface_cache` (or any path with 100GB+ space)
3. Restart terminal/IDE
4. Re-run download (will use new cache location)

### Or Use OneDrive?

**Not Recommended** for this use case:
- ❌ OneDrive is a **sync service**, not raw storage
- ❌ 23GB files cause sync issues and conflicts
- ❌ Processing from synced location is slower
- ❌ May sync to cloud unnecessarily

**Better alternatives:**
- ✅ Use external drive (USB 3.0, SSD)
- ✅ Use different internal drive (D:, E:, etc.)
- ✅ Use the cache directly (no copy needed)

## Option 3: Process in Streaming Mode

The `process_fnspid.py` script already uses **streaming chunked processing**:
- Reads 50,000 rows at a time
- Filters by date while reading
- Never loads entire 23GB file into RAM
- Saves filtered results (much smaller)

**This is already implemented!** No changes needed.

## Verification

### Check Cache Location

```bash
python scripts/find_cache_path.py
```

This will show:
- Cache file path
- File size
- Whether it exists

### Check Disk Space

```bash
# Windows
dir C:\ | find "bytes free"

# Or check specific drive
dir D:\ | find "bytes free"
```

## Summary

**Best Solution:** Use cached file directly (already implemented)
- ✅ Saves 23.2 GB disk space
- ✅ No copying needed
- ✅ Processing script auto-detects cache
- ✅ Works immediately

**If C: drive is full:**
- Move cache to different drive using `HF_HOME` environment variable
- Or use external drive

**Don't use OneDrive** for this - it's not designed for large dataset files.
