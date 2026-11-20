/**
 * 鲸鲨漫剧桌面壳 ↔ 原型桥接层
 *
 * 设计原则：
 * 1. 不修改原型任何业务代码——只包装全局 act()，按动作映射到引擎 API。
 * 2. 浏览器预览时自动尝试连接 127.0.0.1:7420（便于 Playwright 验证）；
 *    Tauri 环境则通过 IPC 获取端口与令牌，令牌不经过 HTTP 端点。
 * 3. 引擎不可用时全部降级为原型自带的演示动画，并明确提示，不假装成功。
 */
(function () {
  "use strict";
  var B = (window.__BRIDGE__ = {
    online: false,
    base: "",
    token: "",
    projectId: null,
    lastWork: null,
    error: null,
    mode: "booting",
  });
  function tip(msg) {
    if (typeof window.toast === "function") window.toast(msg);
    else console.log("[bridge]", msg);
  }
  function invoke(cmd, args) {
    var fn =
      (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke) ||
      (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke);
    return fn ? fn(cmd, args || {}) : Promise.reject(new Error("当前不在桌面壳中"));
  }
  function tipLater(msg) { setTimeout(function () { tip(msg); }, 0); }
  function setStatus(text, connected) {
    var el = document.querySelector(".status");
    if (!el) return;
    el.innerHTML = "<i></i>" + text;
    el.style.color = connected ? "" : "var(--ink3)";
  }
  /** 统一 API 调用：失败返回 null，由调用方决定降级路径。 */
  async function api(path, opts) {
    if (!B.online) return null;
    opts = opts || {};
    try {
      var res = await fetch(B.base + path, {
        method: opts.method || "GET",
        headers: {
          "Content-Type": "application/json",
          "X-Local-Token": B.token,
        },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      if (!res.ok) {
        var txt = await res.text();
        throw new Error(res.status + " " + txt.slice(0, 140));
      }
      return await res.json();
    } catch (e) {
      B.error = String((e && e.message) || e);
      console.warn("[bridge] API 失败:", path, B.error);
      return null;
    }
  }
  function state() {
    return typeof S !== "undefined" ? S : {};
  }
  async function bootstrap() {
    var info = null;
    // 路径 A：Tauri 桌面壳（端口与令牌由 Rust 命令直接返回）
    if (window.__TAURI_INTERNALS__ || window.__TAURI__) {
      try {
        info = await invoke("start_engine");
        B.mode = "tauri";
      } catch (e) {
        B.error = String((e && e.message) || e);
      }
    } else {
      // 路径 B：浏览器预览（引擎需手动启动；仅用于开发验收）
      B.mode = "browser";
      try {
        var h = await fetch("http://127.0.0.1:7420/health", { cache: "no-store" });
        if (h.ok) {
          var t = await fetch("http://127.0.0.1:7420/api/local-token", { cache: "no-store" });
          var j = await t.json();
          info = { base_url: "http://127.0.0.1:7420", token: j.token, running: true };
        }
      } catch (e) {
        B.error = "未检测到本地引擎（浏览器预览为演示模式）";
      }
    }
    if (info && info.running && info.base_url && info.token) {
      B.online = true;
      B.base = info.base_url;
      B.token = info.token;
      setStatus("本地引擎已连接", true);
      tip("已连接本机引擎，你的项目和密钥都保存在这台电脑");
    } else {
      setStatus("演示模式", false);
      tip(B.error || "本地引擎未启动，当前为界面演示模式");
    }
  }
  /** 包装原型交互入口：先调用真实 API，再保留原有 UI 反馈与动画。 */
  var rawAct = window.act;
  if (typeof rawAct !== "function") {
    console.error("[bridge] 未找到原型 act()，桥接失败");
    return;
  }
  window.act = async function act(a, arg) {
    var s = state();
    try {
      switch (a) {
        // ── 项目 ──────────────────────────────────────────────
        case "create": {
          var idea = (document.querySelector("#idea") || {}).value || "";
          idea = idea.trim();
          if (idea) {
            var created = await api("/api/projects", {
              method: "POST",
              body: { idea: idea, template_id: "life_3ep" },
            });
            if (created && created.id) {
              B.projectId = created.id;
              tipLater("项目已写入本机数据库，引擎已连接");
            }
          }
          return rawAct(a, arg);
        }
        case "openProject": {
          var list = await api("/api/projects");
          if (list && list.items && list.items.length) {
            B.projectId = list.items[0].id;
          }
          return rawAct(a, arg);
        }
        // ── 充值：完全由后端驱动，避免 UI 与账本双份累加 ──────
        case "payConfirm": {
          var pay = await api("/api/wallet/recharge", {
            method: "POST",
            body: { plan_id: s.plan || "p1" },
          });
          var modal = document.querySelector("#pay");
          if (modal) modal.classList.remove("open");
          if (pay && typeof pay.balance === "number") {
            var b = document.querySelector(".balance b");
            if (b) b.textContent = pay.balance.toFixed(1);
            tipLater("额度已到账，本地账本已更新 +" + Math.round(pay.amount));
          } else {
            rawAct(a, arg); // 降级：保留演示动画
          }
          return;
        }
        // ── 生成：真实提交走引擎，进度动画保留为演示 ──────────
        case "startGen": {
          var gen = await api("/api/generation/submit", {
            method: "POST",
            body: {
              prompt: "人的一生 · 黄昏院子里的孩子",
              duration_s: 5,
              ratio: s.ratio || "9:16",
              importance: "key",
            },
          });
          if (gen) {
            tipLater("已提交本机引擎：" + (gen.route_reason || "任务已受理"));
          }
          return rawAct(a, arg);
        }
        // ── 导出：落库到作品库 ────────────────────────────────
        case "doExport": {
          if (B.projectId) {
            var exp = await api("/api/projects/" + B.projectId + "/export", {
              method: "POST",
              body: { ratio: s.ratio || "9:16", with_subtitle: true, ai_badge: true },
            });
            if (exp && exp.work_id) {
              B.lastWork = exp;
              tipLater(
                exp.demo
                  ? "演示成片已存入作品库（视频槽还是模拟，尚未生成真实画面）"
                  : "成片已存入本机作品库（AI 标识已自动写入）"
              );
            }
          }
          return rawAct(a, arg);
        }
        // ── 对话：只做意图改写，写操作仍需用户确认 ────────────
        case "say": {
          var msg = (document.querySelector("#msg") || {}).value || "";
          msg = msg.trim();
          if (msg) {
            var chat = await api("/api/chat", {
              method: "POST",
              body: { message: msg, project_id: B.projectId },
            });
            if (chat && chat.intent) {
              tipLater("助手理解：" + (chat.intent.confirm || chat.intent.op) + "（需你确认后执行）");
            }
          }
          return rawAct(a, arg);
        }
        // ── 模型设置 ──────────────────────────────────────────
        case "testKey": {
          var probe = await api("/api/model-configs/video/test", { method: "POST" });
          if (probe) {
            tipLater(
              "连接测试" +
                (probe.ok ? "通过" : "失败") +
                (probe.price_hint ? " · " + probe.price_hint : "")
            );
          }
          return rawAct(a, arg);
        }
        case "saveSettings": {
          var slots = { text: "text", image: "image", video: "video", voice: "speech" };
          var saved = 0;
          for (var g in slots) {
            var v = (s.settings || {})[g];
            if (!v) continue;
            var r = await api("/api/model-configs/" + slots[g], {
              method: "PUT",
              body: {
                source: v === "key" ? "owned" : v === "local" ? "local" : "proxy",
                provider_kind: v === "local" ? "ollama" : "openai_compat",
                name: g + " · " + v,
                endpoint: null,
                credential: null, // 原型展示的是掩码密钥，不回写假密钥
              },
            });
            if (r && r.saved) saved++;
          }
          if (saved) tipLater("已保存 " + saved + " 项配置（密钥仍以本机加密方式保管）");
          return rawAct(a, arg);
        }
        // ── 本地文件：走 Tauri 原生命令 ───────────────────────
        case "umFolder": {
          document.querySelector("#usermenu").classList.remove("open");
          try {
            var dir = await invoke("open_data_folder");
            tipLater("已打开数据文件夹：" + dir);
          } catch (e) {
            tipLater("数据文件夹：文档 / 鲸鲨漫剧");
          }
          return;
        }
        case "download": {
          try {
            var works = await invoke("open_works_folder");
            tipLater("已打开作品库文件夹：" + works);
          } catch (e) {
            rawAct(a, arg);
          }
          return;
        }
        // ── 发布文案：取引擎锁定的合规文案 ────────────────────
        case "copyCap": {
          if (B.lastWork && B.lastWork.work_id) {
            var cap = await api("/api/works/" + B.lastWork.work_id + "/caption");
            if (cap && cap.caption && navigator.clipboard) {
              try { await navigator.clipboard.writeText(cap.caption); } catch (e) {}
              tipLater("发布文案已复制（含 AI 生成声明）");
              return;
            }
          }
          return rawAct(a, arg);
        }
      }
    } catch (e) {
      console.error("[bridge] 动作失败:", a, e);
      tipLater("这一步没能连上引擎，已切换为演示模式");
    }
    return rawAct(a, arg);
  };
  bootstrap();
})();
