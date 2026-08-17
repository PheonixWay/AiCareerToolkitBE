import json
from .models import JDExtractionModel 
from app.core.aiClient import client

def extract_jd_service(raw_text: str) -> JDExtractionModel:
    # Generating JSON Schema from Pydantic model
    schema_dict = JDExtractionModel.model_json_schema()
    schema_json = json.dumps(schema_dict, indent=2)

    # Prompt to extract information from job description
    prompt = f"""
    You are an expert HR assistant and ATS data parser. 
    Extract the relevant information from the job description provided below.
    
    CRITICAL INSTRUCTION: You MUST respond ONLY with a valid JSON object. 
    The JSON object must strictly follow and validate against this JSON Schema:
    
    {schema_json}

    Job Description:
    {raw_text}
    """

    # Calling AI Client
    # response = client.chat.completions.create(
    #     model="llama-3.1-8b-instant",
    #     messages=[
    #         {
    #             "role": "system", 
    #             "content": "You are a highly analytical AI that strictly outputs valid JSON matching the exact schema provided by the user, without any markdown formatting or extra text."
    #         },
    #         {"role": "user", "content": prompt}
    #     ],
    #     response_format={"type": "json_object"},
    #     temperature=0.1 # Low temperature ensures strict fact extraction
    # )

    try:
        # Try best model first
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a highly analytical AI that strictly outputs valid JSON matching the exact schema provided by the user, without any markdown formatting or extra text."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1 # Low temperature ensures strict fact extraction
        )
    except Exception as e:
        if "404" in str(e) or "model_not_found" in str(e):
            print("70B Model is down/busy. Switching to 8B Instant fallback...")
            # fallback to other model
            response = client.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a highly analytical AI that strictly outputs valid JSON matching the exact schema provided by the user, without any markdown formatting or extra text."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1 # Low temperature ensures strict fact extraction
            )
        else:
            raise e


    result_text = response.choices[0].message.content
    
    if result_text is None:
        raise ValueError("The model returned an empty response body.")

    # validate JSON string and convert to Pydantic model
    return JDExtractionModel.model_validate_json(result_text)