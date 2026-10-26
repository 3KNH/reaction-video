# Quy trình dựng video khảo sát nội thất

Quy trình này dựng lại video dọc 9:16 từ sáu clip, kịch bản tiếng Việt, lời đọc **nam Gia Huy** của ZeroTTS và bố cục HyperFrames. File tải cuối là `workflow/work/final-download.mp4`. Mỗi lần chạy dùng clip trong checkout hiện có; không tạo thêm Git worktree.

## Đầu vào

Cần Python 3.10+, Node.js 22+, npm, FFmpeg/FFprobe và Chromium. Đặt video trong `workflow/input/` theo tên trong `config.json`:

| Tên file | Nội dung trong bộ tư liệu hiện tại |
|---|---|
| `apartment.mp4` | Khảo sát hiện trạng căn hộ MT Eatmark City |
| `villa-survey.mp4` | Khảo sát biệt thự Vinhomes Vũ Yên |
| `villa-work.mp4` | Thi công và lát sàn biệt thự Vinhomes |
| `interior.mp4` | THIẾT KẾ & THI CÔNG NỘI THẤT |
| `wall.mp4` | Modern PVC Marble Wall Sheets |
| `tv-design.mp4` | top 10 tv unit design ideas |

Sửa `workflow/example-script.txt` trước lần chạy đầu, hoặc sửa `workflow/work/project/script.txt` sau `prepare`. **Mỗi đoạn văn là một cảnh** và phải có một mục tương ứng trong `config.json`. Trong `config.json`, đổi `sections[].source` để chọn clip cho từng cảnh; `usable_seconds` loại bỏ phần cuối hỏng/đen của nguồn. Clip biệt thự và ảnh mẫu chỉ là tư liệu minh họa, không chứng minh những thông số của căn hộ trong lời bình.

## Chạy từng bước

Từ gốc repository:

```bash
python -m venv workflow/work/.venv
workflow/work/.venv/bin/python -m pip install -r workflow/requirements.txt
workflow/work/.venv/bin/python workflow/run.py prepare
workflow/work/.venv/bin/python workflow/run.py review
```

`prepare` xác minh, cắt phần không dùng và sao chép sáu clip; `review` tạo `work/inventory.json`, `work/source-transcripts.json`, sáu ảnh mẫu mỗi clip trong `work/review-frames/` và `work/source-review.md`. Đọc clip đầy đủ, nghe lại bản bóc băng tự động, điền tóm tắt một câu cho từng clip trong `source-review.md` **trước khi dựng**. Sửa `config.json` nếu cảnh hoặc thứ tự chưa đúng. Giữ nhãn “Tư liệu minh họa” khi sử dụng công trình khác.

Sau khi duyệt nguồn và kịch bản:

```bash
workflow/work/.venv/bin/python workflow/run.py tts
workflow/work/.venv/bin/python workflow/run.py align
workflow/work/.venv/bin/python workflow/run.py compose
workflow/work/.venv/bin/python workflow/run.py render
```

`tts` tải mô hình ZeroTTS đã xác thực qua Hugging Face (~900 MB) lần đầu và đọc toàn bộ kịch bản bằng giọng `giahuy`. `align` dùng Whisper để ước lượng mốc từng từ, ghi `work/narration-giahuy/asr-check.json`; bước này chỉ dùng để căn thời gian, **chữ hiển thị vẫn lấy từ kịch bản gốc**. `compose` tạo video nguồn lặp đúng thời lượng, chia chữ thành tối đa bốn từ mỗi cụm, chạy HyperFrames lint/validate/inspect. `render` xuất MP4 có âm thanh rồi nén bản tải. Các file nguồn, mô hình, cache và kết quả trong `workflow/work/` được bỏ qua bởi Git.

Sau khi render, xem đầu/cuối và từng điểm chuyển cảnh, nghe kỹ thuật ngữ như MDF, Melamine, No-line và Picomat, kiểm tra phụ đề không lệch hoặc che mặt. Chỉ đưa video lên GitHub hoặc dịch vụ khác khi đã quyết định rõ phạm vi chia sẻ; lệnh trong quy trình không tự xuất bản công khai.

Kịch bản mẫu dài 815 từ; bản giọng nam thử nghiệm dài khoảng **211,5 giây**, vượt mốc 3 phút của một số định dạng Short. Nếu đích đăng yêu cầu tối đa 3 phút, rút gọn kịch bản rồi chạy lại từ `tts`; quy trình không tự cắt mất câu.

## Kiểm tra và giới hạn

- `workflow/run.py` dừng nếu thiếu clip, ASR chênh hơn 5% số từ, kiểm tra HyperFrames lỗi, hoặc MP4 thiếu kênh hình/tiếng.
- Mô hình TTS không tự xác minh các khẳng định về vật liệu, kích thước và tiến độ trong kịch bản. Những chi tiết đó cần hồ sơ công trình và hình đúng cảnh.
- Bản nhận dạng lời nói có thể nghe sai từ chuyên ngành. Người dựng cần nghe duyệt âm thanh trước khi đăng.
- Màu, font và vị trí chữ mặc định trong `DESIGN.md`/`build.py`; đổi theo nhận diện thương hiệu trước khi phát hành chính thức.
