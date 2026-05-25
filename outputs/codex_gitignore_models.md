# Codex Task: Gitignore model weights and commit outputs/ archives

## Background

Two issues appeared after the vision stack was installed:

1. `yolov8n.pt` (YOLO v8 nano model weights, ~6MB) was auto-downloaded by
   ultralytics to the repo root when VisionSensor first ran. Model weight files
   must never be committed — they are large, binary, and regenerable.

2. Three Codex prompt archives in `outputs/` are untracked:
   - `outputs/codex_doc_polish.md`
   - `outputs/codex_document_parsing.md`
   - `outputs/codex_media_routing.md`

   These are build-history records documenting what was implemented. They should
   be committed as documentation.

## Changes required

### 1. `.gitignore` — add model weight patterns

Add this block after the existing `# Godot editor cache` section:

```
# Model weights (auto-downloaded, never commit)
*.pt
*.pth
*.onnx
*.bin
models/
```

### 2. Stage and commit

```
git add .gitignore outputs/codex_doc_polish.md outputs/codex_document_parsing.md outputs/codex_media_routing.md
git reset HEAD world_models/config.py
git commit -m "chore: gitignore model weights, commit outputs/ prompt archives

- Add *.pt, *.pth, *.onnx, *.bin, models/ to .gitignore
  (yolov8n.pt auto-downloaded by ultralytics; must not be tracked)
- Commit three Codex prompt archives as build-history documentation"
git push origin main
```

## Security reminder

Do not stage or commit `world_models/config.py`. Run `git status` before
committing to confirm only the four listed files are staged.
