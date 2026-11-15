import json

cells = [
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "# FINAL - Test Notebook Ricostruito\n",
            "\n",
            "Notebook rigenerato perché il precedente aveva errori di formato JSON."
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import sys\n",
            "import os\n",
            "\n",
            "print('Python:', sys.executable)\n",
            "print('Cartella corrente:', os.getcwd())"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "from agents import classificator, translator, causal_A"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "from dotenv import load_dotenv\n",
            "load_dotenv()"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "async def main(task=None):\n",
            "    session = causal_A.create_session()\n",
            "\n",
            "    if task is None:\n",
            "        task = input('Inserisci la tua domanda causale: ')\n",
            "\n",
            "    print(f'\\n🎯 TASK:\\n{task}\\n')\n",
            "\n",
            "    print('🔄 1. Traduzione in corso...')\n",
            "    translation_a = (\n",
            "        await translator.run(\n",
            "            f'Create a dictionary following your instruction of the query: {task}',\n",
            "            session=session\n",
            "        )\n",
            "    ).text\n",
            "    print(f'📝 Dictionary:\\n{translation_a}\\n')\n",
            "\n",
            "    print('🔄 2. Classificazione in corso...')\n",
            "    label_a = (\n",
            "        await classificator.run(\n",
            "            f'Classify the following query using your instructions: {task}',\n",
            "            session=session\n",
            "        )\n",
            "    ).text\n",
            "    print(f'🏷️ Label:\\n{label_a}\\n')\n",
            "\n",
            "    print('🔄 3. Calcolo causale in corso...')\n",
            "    prompt = (\n",
            "        f'Provide the precise answer to the user task ({task}) '\n",
            "        f'using your TOOLS with the following parameters -> '\n",
            "        f'label: {label_a}, features: {translation_a}. '\n",
            "        f'After that give the causal explanation of this answer.'\n",
            "    )\n",
            "    causal_answer_a = (\n",
            "        await causal_A.run(prompt, session=session)\n",
            "    ).text\n",
            "\n",
            "    print(f'✅ Risposta finale:\\n{causal_answer_a}\\n')\n",
            "\n",
            "    return translation_a, label_a, causal_answer_a"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Test con la prima query del ground truth (CP1)\n",
            "await main('Given that the driving quality is normal, how likely is it that the age of the driver is senior?')"
        ]
    }
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.10.0"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 5
}

with open("FINAL_test.ipynb", "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=2, ensure_ascii=False)

print("✅ Creato FINAL_test.ipynb con successo!")
print("Ora puoi aprirlo con Jupyter Notebook.")