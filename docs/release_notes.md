# Release Notes

## v0.8.4 (2026-02-20)
- 新增 AI Prompt 配置能力：支持在设置页自定义 system/user prompt、temperature、tags_limit，并支持重置默认值。
- 新增 LLM 运行时配置：支持在设置页配置 `base_url`、`model_name`，并展示 API Key 是否已配置。
- 图片详情页支持“仅本次覆盖生成”高级参数；元数据返回 `prompt_source` 与 `llm_source` 便于追踪来源。
- Gallery 弹层新增单击图片专注模式：仅隐藏左下角 AI 标题/标签覆层，保留右下角工具按钮可操作。
- 新增 `tests/test_prompt_config.py`，覆盖 prompt/llm 配置 API 与元数据来源优先级。
