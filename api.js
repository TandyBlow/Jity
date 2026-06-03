const API = {

  async callLLM(systemPrompt, history) {
    const messages = [
      { role: "system", content: systemPrompt },
      ...history.map(h => ({
        role: h.role === "model" ? "assistant" : "user",
        content: h.content
      }))
    ];

    const response = await fetch(`${CONFIG.LLM_BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${CONFIG.DEEPSEEK_API_KEY}`
      },
      body: JSON.stringify({
        model: CONFIG.LLM_MODEL,
        messages,
        temperature: 0.3,
        max_tokens: 1024,
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(`LLM error: ${err.error?.message || response.status}`);
    }

    const data = await response.json();
    const text = data.choices?.[0]?.message?.content || "";

    const cleaned = text.replace(/```json|```/g, "").trim();
    // DeepSeek 可能输出思考内容，需要去掉
    const withoutThink = cleaned.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
    try {
      return JSON.parse(withoutThink);
    } catch (e) {
      throw new Error("模型返回格式解析失败: " + withoutThink.slice(0, 200));
    }
  },

  async generateImage(scenePrompt) {
    const fullPrompt = CONFIG.IMAGE_STYLE_PREFIX + scenePrompt;

    const response = await fetch("https://api.siliconflow.cn/v1/images/generations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${CONFIG.SILICONFLOW_API_KEY}`
      },
      body: JSON.stringify({
        model: CONFIG.IMAGE_MODEL,
        prompt: fullPrompt,
        negative_prompt: CONFIG.IMAGE_NEGATIVE_PROMPT,
        image_size: "1024x576",
        num_inference_steps: 4,
        num_images: 1,
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(`图像生成 error: ${err.error?.message || response.status}`);
    }

    const data = await response.json();
    const imageUrl = data.images?.[0]?.url;
    if (!imageUrl) throw new Error("未返回图片 URL");
    return imageUrl;
  }

};
