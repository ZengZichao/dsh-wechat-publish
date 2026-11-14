# 配置公众号凭据与 IP 白名单

发布功能要求本机能用公众号的接口凭据，并且出口 IP 已在后台白名单里。你需要：公众号管理员权限、能改本机 shell 配置、一个固定的公网出口 IP。

1. 登录公众号后台，打开 **开发 → 基本配置**。

2. 复制 **AppID**。

3. 生成或复制 **AppSecret**。Secret 只显示一次，没存过就重新生成；重置会让旧 Secret 立即失效。

4. 在同一个 **基本配置** 页找到 **IP 白名单**，把本机公网 IP 加进去。

   > 提示：换 Wi-Fi、重拨号、切到公司网络后出口 IP 会变。发布报 `40164` 时先回这一步核对；报 `40013` 则核对 AppID 与 Secret 是否属于同一个账号。

5. 把两个值写进 shell 配置。

   ```bash
   echo 'export WECHAT_APP_ID="wx你的AppID"' >> ~/.zshrc
   echo 'export WECHAT_APP_SECRET="你的AppSecret"' >> ~/.zshrc
   ```

   > 提示：用 `~/.zshrc` 是因为 DSH 通常从登录 shell 启动。用 bash 的话改成 `~/.bash_profile`。

6. 让当前终端读到新变量。

   ```bash
   source ~/.zshrc
   ```

7. 完全退出并重启 DSH，让新进程继承环境变量。

8. 打开 **公众号发布**，切到 **设置**，在 **凭据** 组确认 AppID 显示为掩码、AppSecret 显示 **已设置**，而不是 **未设置**。

   > **配图**：设置页的凭据组。（替代文本：设置页「凭据」分组两行，AppID 显示前后各两位、中间为星号的掩码，AppSecret 右侧显示「已设置」。）

9. 切到 **草稿箱**，点 **刷新**，能看到草稿列表。

**结果：** **设置** 的凭据组不再显示 **未设置**；**草稿箱** 能列出内容；**预览** 页顶部的 **发布** 按钮从不可点变为可点。

## 相关文章

- [排查公众号发布报错](troubleshoot-publish-errors.md)：40164、40013、按钮不可点、凭据不完整。
- [把 Markdown 文章发布到公众号草稿箱](publish-a-markdown-article.md)
- [查阅环境变量与解释器顺序](reference-environment-variables.md)
