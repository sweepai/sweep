export OPENAI_DO_HAVE_32K_MODEL_ACCESS=true 
modal deploy sweepai/api.py
modal deploy sweepai/utils/utils.py
modal deploy sweepai/core/vector_db.py
modal deploy sweepai/app/backend.py
