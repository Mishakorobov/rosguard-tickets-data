#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — Валидатор целостности и генератор манифеста билетов Росгвардии.
Проверяет структуру questions.json и questions_private.json, вычисляет SHA-256
и обновляет questions_manifest.json перед коммитом.
"""

import os
import sys
import json
import hashlib
from datetime import datetime

def compute_sha256(filepath: str) -> str:
    """Вычисляет хэш SHA-256 файла."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()

def validate_questions_file(filepath: str, min_expected_questions: int, name: str):
    """Строгая валидация структуры файла вопросов."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Файл {filepath} ({name}) не найден!")

    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON в {filepath}: {e}")

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError(f"Файл {filepath} должен содержать непустой массив разделов.")

    total_questions = 0
    section_ids = set()

    for sec_idx, section in enumerate(data):
        if not isinstance(section, dict):
            raise ValueError(f"Раздел #{sec_idx} не является объектом JSON в {filepath}")

        sec_id = section.get('id')
        title = section.get('title')
        questions = section.get('questions')

        if not sec_id or not isinstance(sec_id, str):
            raise ValueError(f"Раздел #{sec_idx} имеет некорректный 'id' в {filepath}")
        if sec_id in section_ids:
            raise ValueError(f"Дублирующийся id раздела '{sec_id}' в {filepath}")
        section_ids.add(sec_id)

        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError(f"Раздел '{sec_id}' имеет пустое название в {filepath}")

        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError(f"Раздел '{sec_id}' не содержит вопросов в {filepath}")

        for q_idx, q in enumerate(questions):
            total_questions += 1
            if not isinstance(q, dict):
                raise ValueError(f"Вопрос #{q_idx} в разделе '{sec_id}' не является объектом")

            q_id = q.get('id')
            q_text = q.get('text')
            options = q.get('options')
            correct_idx = q.get('correctAnswerIndex')

            if not q_id:
                raise ValueError(f"В вопросе #{q_idx} раздела '{sec_id}' отсутствует 'id'")

            if not q_text or not isinstance(q_text, str) or not q_text.strip():
                raise ValueError(f"Вопрос {q_id} имеет пустой текст")

            if not isinstance(options, list) or len(options) < 2:
                raise ValueError(f"Вопрос {q_id} имеет менее 2 вариантов ответа ({options})")

            for opt_idx, opt in enumerate(options):
                if not isinstance(opt, str) or not opt.strip():
                    raise ValueError(f"Вопрос {q_id}: пустой вариант ответа #{opt_idx}")

            if not isinstance(correct_idx, int) or correct_idx < 0 or correct_idx >= len(options):
                raise ValueError(
                    f"Вопрос {q_id}: некорректный correctAnswerIndex={correct_idx} при {len(options)} вариантах"
                )

    if total_questions < min_expected_questions:
        raise ValueError(
            f"В файле {name} обнаружено всего {total_questions} вопросов, что меньше порога {min_expected_questions}!"
        )

    print(f"[{name}] Валидация успешна: {len(data)} разделов, {total_questions} вопросов.")
    return len(data), total_questions

def update_manifest(root_dir: str):
    """Обновляет questions_manifest.json актуальными хэшами и количеством вопросов."""
    manifest_path = os.path.join(root_dir, 'questions_manifest.json')
    vohr_path = os.path.join(root_dir, 'questions.json')
    private_path = os.path.join(root_dir, 'questions_private.json')

    # Валидация ВОХР (минимум 200 вопросов)
    vohr_sections, vohr_count = validate_questions_file(vohr_path, 200, "ВОХР")
    vohr_sha256 = compute_sha256(vohr_path)

    # Валидация ЧОП (минимум 190 вопросов)
    private_sections, private_count = validate_questions_file(private_path, 190, "ЧОП")
    private_sha256 = compute_sha256(private_path)

    if not os.path.exists(manifest_path):
        manifest = {
            "year": datetime.now().year,
            "version": "1.1.0",
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
            "rosguard_page_url": "https://rosguard.gov.ru/page/index/licenzionnorazreshitelnaya-rabota/",
            "rosguard_pdf_url": "https://rosguard.gov.ru/uploads/2026/08/voprosydlyaperiodicheskojjproverki.pdf",
            "vohr": {},
            "private_guard": {}
        }
    else:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    manifest["updated_at"] = today

    # Обновляем ссылки на новый публичный репозиторий rosguard-tickets-data
    manifest["vohr"] = {
        "url": "https://raw.githubusercontent.com/Mishakorobov/rosguard-tickets-data/main/questions.json",
        "sha256": vohr_sha256,
        "questions_count": vohr_count,
        "sections_count": vohr_sections
    }

    manifest["private_guard"] = {
        "url": "https://raw.githubusercontent.com/Mishakorobov/rosguard-tickets-data/main/questions_private.json",
        "sha256": private_sha256,
        "questions_count": private_count,
        "sections_count": private_sections
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print("==================================================================")
    print("Манифест questions_manifest.json успешно обновлен:")
    print(f"  • ВОХР: {vohr_count} вопросов ({vohr_sections} разделов), SHA-256: {vohr_sha256}")
    print(f"  • ЧОП:  {private_count} вопросов ({private_sections} разделов), SHA-256: {private_sha256}")
    print("==================================================================")

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        update_manifest(base_dir)
        sys.exit(0)
    except Exception as e:
        print(f"[ОШИБКА ВАЛИДАЦИИ]: {e}", file=sys.stderr)
        sys.exit(1)
