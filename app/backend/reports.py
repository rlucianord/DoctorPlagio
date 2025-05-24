import json
# Lógica para generar informes (podría usar bibliotecas como ReportLab)
# Por ahora, simplemente devolvemos los resultados en formato JSON
def generate_plagiarism_report(results):
    return {
        "plagiarism_percentage_text": results.plagiarism_percentage_text,
        "plagiarism_details_text": json.loads(results.plagiarism_details_text) if results.plagiarism_details_text else [],
        "ai_detection_percentage": results.ai_detection_percentage,
        "ai_detection_details": results.ai_detection_details
    }