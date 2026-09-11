const CONFIG = {
  // ===== API Keys =====
  // 使用前请替换为你自己的 API Key
  DEEPSEEK_API_KEY: "sk-your-deepseek-api-key",
  SILICONFLOW_API_KEY: "sk-your-siliconflow-api-key",

  // ===== 模型配置 =====
  LLM_MODEL: "deepseek-v4-flash",
  LLM_BASE_URL: "https://api.deepseek.com",
  IMAGE_MODEL: "Kwai-Kolors/Kolors",

  IMAGE_STYLE_PREFIX: "pencil sketch, monochrome, hand-drawn linework, atmospheric, dark horror tone, first person perspective, detailed crosshatching, vintage illustration, ",
  IMAGE_NEGATIVE_PROMPT: "color, colorful, painting, digital art, anime, cartoon, blurry, low quality, watermark, text, UI elements, people in foreground",

  INITIAL_SANITY: 80,
  INITIAL_HEALTH: 100,
};
