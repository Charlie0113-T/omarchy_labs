.pragma library

// Panel text in the same four languages as the test tool. The language follows
// the system locale; the test itself asks again in its terminal.

var LANGUAGES = ["en", "zh-CN", "zh-TW", "ja"];

var TEXT = {
  "title": ["Omarchy Lab", "Omarchy Lab", "Omarchy Lab", "Omarchy Lab"],
  "ready": ["Ready · tests run in a terminal", "就绪 · 测试在终端中运行", "就緒 · 測試在終端機中執行", "準備完了 · テストはターミナルで実行"],
  "running": ["A test is running", "测试正在运行", "測試正在執行", "テスト実行中"],
  "runHeader": ["RUN A TEST", "运行测试", "執行測試", "テストを実行"],
  "typical": ["Typical: CPU, memory, disk", "典型测试：CPU、内存、磁盘", "典型測試：CPU、記憶體、磁碟", "典型テスト：CPU・メモリ・ディスク"],
  "typicalTip": ["About 10–15 minutes. Needs fio and sysbench.", "约 10–15 分钟。需要 fio 和 sysbench。", "約 10–15 分鐘。需要 fio 與 sysbench。", "約 10〜15 分。fio と sysbench が必要です。"],
  "daily": ["Daily: coding + browser + update load", "日常测试：编程＋浏览器＋更新负载", "日常測試：寫程式＋瀏覽器＋更新負載", "日常テスト：プログラミング＋ブラウザ＋更新負荷"],
  "dailyTip": ["About 5 minutes. Opens a Chromium test window; keep it visible.", "约 5 分钟。会打开 Chromium 测试窗口，请保持可见。", "約 5 分鐘。會開啟 Chromium 測試視窗，請保持可見。", "約 5 分。Chromium のテストウィンドウが開くので、表示したままにしてください。"],
  "agent": ["Agent: local coding replay", "Agent：本机编程回放", "Agent：本機程式重播", "Agent：ローカルのプログラミング再生"],
  "agentTip": ["About 1 minute. Never calls a model.", "约 1 分钟。不调用模型。", "約 1 分鐘。不呼叫模型。", "約 1 分。モデルは呼び出しません。"],
  "agentLive": ["Agent with your model (uses quota)", "Agent + 你的模型（消耗额度）", "Agent + 你的模型（消耗額度）", "Agent＋自分のモデル（利用枠を消費）"],
  "agentLiveTip": ["Calls your configured Pi model. Asks before starting.", "调用你配置的 Pi 模型，开始前会再确认。", "呼叫你設定的 Pi 模型，開始前會再確認。", "設定済みの Pi モデルを呼び出します。開始前に確認します。"],
  "resultsHeader": ["RESULTS", "结果", "結果", "結果"],
  "openReport": ["Open latest report", "打开最新报告", "開啟最新報告", "最新のレポートを開く"],
  "openFolder": ["Open results folder", "打开结果文件夹", "開啟結果資料夾", "結果フォルダーを開く"],
  "share": ["Share latest result on GitHub", "在 GitHub 分享最新结果", "在 GitHub 分享最新結果", "最新の結果を GitHub で共有"],
  "shareTip": ["Copies the report and opens a new issue. Review before submitting.", "复制报告并打开新 Issue，提交前请检查。", "複製報告並開啟新 Issue，送出前請檢查。", "レポートをコピーして新しい Issue を開きます。送信前に確認してください。"],
  "stop": ["Stop the running test", "停止正在运行的测试", "停止正在執行的測試", "実行中のテストを停止"],
  "stopTip": ["Cleans up and saves a partial report.", "会清理并保存部分报告。", "會清理並儲存部分報告。", "後片付けをして途中までのレポートを保存します。"]
};

function language(localeName) {
  var tag = String(localeName || "").replace("_", "-").toLowerCase();
  if (tag === "zh-tw" || tag === "zh-hk" || tag === "zh-mo" || tag.indexOf("zh-hant") === 0) return "zh-TW";
  if (tag.indexOf("zh") === 0) return "zh-CN";
  if (tag.indexOf("ja") === 0) return "ja";
  return "en";
}

function text(code, key) {
  var entry = TEXT[key];
  if (!entry) return key;
  var index = LANGUAGES.indexOf(code);
  return entry[index < 0 ? 0 : index];
}
