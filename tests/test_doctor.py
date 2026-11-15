from cinefacts import doctor as d


def test_binary_missing_gives_fail_with_fix():
    c = d.check_binary("ffmpeg", fix="sudo apt install -y ffmpeg", which=lambda n: None)
    assert c.status == "fail" and "apt install -y ffmpeg" in c.fix


def test_ffmpeg_features_missing_libx264():
    c = d.check_ffmpeg_features("V..... libx265", "loudnorm drawtext ass scale crop concat")
    assert c.status == "fail" and "libx264" in c.detail


def test_ffmpeg_features_all_present():
    enc = " V....D libx264  H.264"
    flt = " loudnorm\n drawtext\n ass\n scale\n crop\n concat\n"
    assert d.check_ffmpeg_features(enc, flt).status == "ok"


def test_truncated_model_fails(tmp_path):
    f = tmp_path / "kokoro-v1.0.onnx"
    f.write_bytes(b"x" * 1000)
    c = d.check_model_file(f, 300_000_000)
    assert c.status == "fail" and "setup.sh" in c.fix


def test_missing_model_fails(tmp_path):
    assert d.check_model_file(tmp_path / "none.bin", 1).status == "fail"


def test_env_blank_key_fails():
    assert d.check_env({"PIXABAY_API_KEY": ""}).status == "fail"
    assert d.check_env({"PIXABAY_API_KEY": "k"}).status == "ok"


def test_pixabay_ok():
    c = d.check_pixabay("SECRETKEY", lambda url: (200, '{"totalHits": 5, "hits": []}'))
    assert c.status == "ok"


def test_pixabay_network_error_fails_without_leaking_key():
    def boom(url):
        raise OSError("Name or service not known for " + url)
    c = d.check_pixabay("SECRETKEY", boom)
    assert c.status == "fail"
    assert "SECRETKEY" not in c.detail + c.fix


def test_pixabay_bad_key_fails_without_leaking_key():
    c = d.check_pixabay("SECRETKEY", lambda url: (400, "[ERROR 400] Invalid or missing API key"))
    assert c.status == "fail" and "SECRETKEY" not in c.detail + c.fix


def test_http_requests_send_project_user_agent():
    # Pixabay's Cloudflare returns 403 (error 1010) for the default "Python-urllib" agent.
    req = d._build_request("https://pixabay.com/api/videos/?q=x")
    ua = req.get_header("User-agent")
    assert ua and "CineFacts" in ua and "Python-urllib" not in ua


def test_disk_warn_below_5gib():
    assert d.check_disk(4 * 1024**3).status == "warn"
    assert d.check_disk(20 * 1024**3).status == "ok"


def test_memory_parsed_from_meminfo():
    c = d.check_memory("MemTotal:        3984588 kB\nMemFree: 1 kB\n")
    assert c.status == "ok" and "3.8" in c.detail


def test_font_detection():
    assert d.check_font("/usr/share/fonts/opentype/inter/Inter-Bold.otf: Inter:style=Bold").status == "ok"
    assert d.check_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf: DejaVu Sans").status == "fail"


def test_rclone_remote_detection():
    assert d.check_rclone_remote("gdrive:\n").status == "ok"
    c = d.check_rclone_remote("")
    assert c.status == "warn" and "rclone config" in c.fix


def test_report_and_exit_code():
    checks = [d.Check("a", "ok", "fine"), d.Check("b", "warn", "meh", "do x"),
              d.Check("c", "fail", "bad", "do y")]
    out = d.format_report(checks)
    assert "[ OK ] a" in out and "[WARN] b" in out and "[FAIL] c" in out
    assert "fix: do y" in out and "fix: do x" in out
    assert d.exit_code(checks) == 1
    assert d.exit_code(checks[:2]) == 0
