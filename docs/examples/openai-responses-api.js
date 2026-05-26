import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const response = await client.responses.create({
  model: process.env.OPENAI_MODEL || "gpt-5.1",
  input: "Какие открытые слои данных городского округа Йошкар-Ола доступны?",
  tools: [
    {
      type: "mcp",
      server_label: "yoshkar_ola_public_data",
      server_description: "Открытые данные городского округа \"Город Йошкар-Ола\".",
      server_url: "https://apiiola.yasg.ru/mcp",
      require_approval: "never",
    },
  ],
});

console.log(response.output_text);
