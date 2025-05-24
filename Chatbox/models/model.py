from venv import logger
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from huggingface_hub import snapshot_download

device = "cuda" if torch.cuda.is_available() else "cpu"

def get_response(prompt=None):
    model_options = [
        {
            "model": "Qwen/Qwen3-8B",
            "task": "text-generation",
            "is_chat_model": True  # Blenderbot doesn't use chat templates
        },
        {
            "model": "Mr-Vicky-01/qwen-conversational-finetuned",
            "task": "text-generation",
            "is_chat_model": True  # Blenderbot doesn't use chat templates
        },
        {
            "model": "reddgr/gemma-2-2b-ft-lora-noticias-es",
            "task": "text-generation",
            "is_chat_model": True
        },
        {
            "model": "Mr-Vicky-01/qwen-conversational-finetuned",
            "task": "text-generation",
            "is_chat_model": True
        }
    ]

    for option in model_options:
        try:
            model_name = option["model"]
            task = option["task"]
            is_chat_model = option["is_chat_model"]
            
            # Download model (if not already cached)
            snapshot_download(repo_id=model_name)
            
            # Load tokenizer and model
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForCausalLM.from_pretrained(
                model_name, 
                device_map="auto", 
                torch_dtype=torch.bfloat16
            )
            
            # Prepare input based on model type
            if is_chat_model:
                # For chat models using chat templates
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt if prompt else "Hello!"}
                ]
                input_text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                # For non-chat models like Blenderbot
                input_text = prompt if prompt else "Hello!"
            
            # Create pipeline
            pipe = pipeline(
                task=task,
                model=model,
                tokenizer=tokenizer,
                device_map="auto"
            )
            
            # Generate response
            response = pipe(
                input_text,
                #max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
            
            # Extract and clean the response
            if isinstance(response, list) and len(response) > 0:
                generated_text = response[0]['generated_text']
                
                # Remove input text from response for chat models
                if is_chat_model:
                    generated_text = generated_text.replace(input_text, "").strip()
                
                return generated_text
                
            return "Sorry, I couldn't generate a response."
            
        except Exception as e:
            logger.warning(f"Failed with {model_name}: {str(e)}")
            continue
    
    return "We're experiencing technical difficulties. Please try again later."

def responder_pregunta_qwen3(pregunta, contexto, max_length=200, temperature=0.7):
    modelo_nombre_qwen3 = "Qwen/Qwen3-8B" # Ejemplo de nombre de modelo
    tokenizer_qwen3 = AutoTokenizer.from_pretrained(modelo_nombre_qwen3)
    modelo_qwen3 = AutoModelForCausalLM.from_pretrained(modelo_nombre_qwen3)
    """Genera una respuesta a una pregunta dado un contexto usando Qwen3."""
    prompt = f"Pregunta: {pregunta}\nContexto: {contexto}\nRespuesta:"
    input_ids = tokenizer_qwen3.encode(prompt, return_tensors="pt")
    outputs = modelo_qwen3.generate(input_ids, max_length=max_length, num_return_sequences=1, temperature=temperature, pad_token_id=tokenizer_qwen3.eos_token_id)
    respuesta = tokenizer_qwen3.decode(outputs[0], skip_special_tokens=True)
    return respuesta.replace(prompt, "").strip()

if __name__ == "__main__":
    pregunta_usuario = "¿Cuántos contratos tiene la empresa  ACQUARELLO?"
    contexto_documento = "Todos los contratos firmados por la empresa desde el ano."
    respuesta_generada_qwen3 = responder_pregunta_qwen3(pregunta_usuario, contexto_documento)
    print(f"Pregunta: {pregunta_usuario}")
    print(f"Contexto: {contexto_documento}")
    print(f"Respuesta Generada por Qwen3: {respuesta_generada_qwen3}")