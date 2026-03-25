import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

class GeminiService:
    """Service for interacting with Google's Gemini API"""
    
    def __init__(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        
        self.behavior_instructions = (
            "You are a precise assistant. "
            "Prioritize factual correctness and clarity. "
            "If uncertain, state assumptions briefly instead of guessing. "
            "Format responses in clean Markdown with professional structure. "
            "Default answer format unless user asks otherwise: "
            "## Summary, ## Key Points, ## Next Steps. "
            "Use bullets for lists and short paragraphs. "
            "Avoid verbose filler."
        )

        # Keep constructor compatible with older google-generativeai versions.
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
    def generate_response(self, prompt, context=None):
        """
        Generate a response using Gemini API
        
        Args:
            prompt (str): User's input/question
            context (list): Previous conversation context
        
        Returns:
            str: Generated response from Gemini
        """
        try:
            # Prepare the prompt with context if available
            if context and len(context) > 0:
                full_prompt = self._build_contextual_prompt(prompt, context)
            else:
                full_prompt = (
                    f"Instructions: {self.behavior_instructions}\n\n"
                    f"User request: {prompt}\n\n"
                    "Return a polished, professional answer with proper section headers."
                )
            
            # Generate response with conservative settings for stable output quality.
            response = self.model.generate_content(
                full_prompt,
                generation_config={
                    'temperature': 0.2,
                    'top_p': 0.9,
                    'max_output_tokens': 2048
                }
            )
            
            # Check if response is valid
            if response and response.text:
                return response.text.strip()
            else:
                return "I could not generate a complete response. Please try again with a more specific question."
                
        except Exception as e:
            print(f"Gemini API error: {e}")
            raise Exception(f"Failed to generate response: {str(e)}")
    
    def _build_contextual_prompt(self, current_prompt, context):
        """Build a prompt with conversation context"""
        context_text = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in context[-10:]  # Last 10 messages for context
        ])
        
        return f"""Instructions:
    {self.behavior_instructions}

    Previous conversation:
{context_text}

Current question: {current_prompt}

    Answer requirements:
    1) Be accurate and concise.
    2) Use clear Markdown sections and bullets.
    3) If information is missing or uncertain, say what is needed.
    4) If code is requested, provide complete runnable snippets.
    5) Make the answer look polished and professional, not a single plain paragraph.

    Please provide your best answer based on the conversation context above."""
    
    def generate_stream_response(self, prompt):
        """Generate streaming response (for future implementation)"""
        # This could be implemented for real-time streaming responses
        pass