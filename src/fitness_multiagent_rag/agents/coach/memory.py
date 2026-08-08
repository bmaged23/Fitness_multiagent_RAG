from fitness_multiagent_rag.memory.sqlite_memory_backend import CoachMemoryBackend

# Single shared instance — stateless, safe to share across the session
memory_backend = CoachMemoryBackend()
