import { Injectable, signal } from '@angular/core';
import { GoogleGenAI } from '@google/genai';

@Injectable({
  providedIn: 'root'
})
export class GeminiService {
  private ai: GoogleGenAI;
  isAnalyzing = signal<boolean>(false);

  constructor() {
    // Assuming environment variable is injected by the build system/environment
    this.ai = new GoogleGenAI({ apiKey: process.env['API_KEY'] || '' });
  }

  async analyzeHeader(headerText: string): Promise<string> {
    if (!process.env['API_KEY']) {
      return "Error: API Key is missing. Cannot contact Gemini.";
    }

    this.isAnalyzing.set(true);
    try {
      const prompt = `
        You are an expert astronomer. Analyze the following FITS header data from an astronomical observation.
        
        HEADER DATA:
        ${headerText}
        
        Please provide a concise summary including:
        1. The Target Object (if specified)
        2. Telescope and Instrument details
        3. Observation Date and Exposure Time
        4. Any notable technical details (filters, coordinates)
        
        Format the output as simple HTML with <strong> tags for keys. Keep it brief and professional.
      `;

      const response = await this.ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: prompt,
      });

      this.isAnalyzing.set(false);
      return response.text || "No analysis generated.";
    } catch (error: any) {
      this.isAnalyzing.set(false);
      console.error("Gemini Error:", error);
      return `Analysis failed: ${error.message}`;
    }
  }
}
