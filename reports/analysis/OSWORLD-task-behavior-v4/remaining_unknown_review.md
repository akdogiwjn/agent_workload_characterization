# OSWorld v4：剩余未知项的补充审查

逐command审计中，以下原样保存的符号在静态Python调用解析层仍记为unknown。它们不含白名单函数调用；不能把这些unknown全算作“遗漏的GUI动作”。

| 模型标签 | DONE | ASK_USER | FAIL | WAIT |
|---|---:|---:|---:|---:|
| MiniMax-M3 | 82 | 26 | 4 | 0 |
| claude-opus-4-7 | 0 | 18 | 0 | 0 |
| claude-sonnet-4-6-max | 0 | 46 | 0 | 0 |
| claude-sonnet-4-6-medium | 0 | 2 | 0 | 0 |
| gpt-5.5 | 0 | 103 | 0 | 0 |
| gpt-5.6 | 0 | 1 | 0 | 0 |
| qwen3.7 | 92 | 9 | 1 | 4265 |

识别依据是原始command内容的完整SHA-256与上述字面符号精确相同，未执行、未解码或依赖模型判断。标记只按保存值统计，不代表任务成功、实际等待时长、正常终止或用户已被询问。

Claude剩余主体是try/属性赋值包装；GPT的293条partial涉及未支持的导入/解码赋值，但其中明确的pyperclip.copy和键盘调用仍单独保留。

原生computer_call包装未知与命令源码已识别并存，两层分母不同。此前734条partial/21条valid是v3旧口径；v4使用独立的command状态，不将它们改称“全部轨迹完整”。

[验证明细](verification.json) · [行为发现](findings.md) · [覆盖报告](summary.md)
