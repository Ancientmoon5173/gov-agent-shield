/**
 * 插件发现测试：验证 OpenClaw 的 bundled plugin 扫描器能识别
 * extensions/govagent-shield 并正确读取 manifest 与入口。
 */

import { describe, expect, it } from "vitest";
import { listBundledPluginMetadata } from "../../src/plugins/bundled-plugin-metadata.js";

describe("govagent-shield plugin discovery", () => {
  it("OpenClaw 扫描器能够发现并加载 govagent-shield 插件", () => {
    const plugins = listBundledPluginMetadata({
      scanDir: "extensions",
    });
    const plugin = plugins.find((entry) => entry.manifest.id === "govagent-shield");

    expect(plugin).toBeDefined();
    expect(plugin?.manifest.name).toBe("GovAgent-Shield");
    expect(plugin?.packageName).toBe("@openclaw/govagent-shield");
    expect(plugin?.source.source).toBe("./index.ts");
  });
});
