"""Citable source statements relevant to observed accessibility conditions.

Summaries are paraphrased from the three user-supplied PDFs. Source URLs point
at published editions; page fragments refer to PDF page numbers where possible.
"""

WHO_PDF = "https://iris.who.int/bitstream/handle/10665/378483/9789240094161-eng.pdf"
ETSI_PDF = "https://www.etsi.org/deliver/etsi_en/301500_301599/301549/03.02.01_60/en_301549v030201p.pdf"
BRUNEL_ARTICLE = "https://doi.org/10.1016/j.csi.2024.103923"


def _who(number, summary):
    page = 15 if number <= 11 else 16
    return {
        "source": "WHO/ITU Implementation toolkit for accessible telehealth services",
        "sourceType": "Toolkit requirement",
        "locator": f"Requirement {number}, p. {5 if number <= 11 else 6}",
        "summary": summary,
        "url": f"{WHO_PDF}#page={page}",
    }


def _etsi(clause, summary, page):
    return {
        "source": "ETSI EN 301 549 V3.2.1",
        "sourceType": "Standard requirement",
        "locator": f"Clause {clause}, p. {page}",
        "summary": summary,
        "url": f"{ETSI_PDF}#page={page}",
    }


def _brunel(locator, summary):
    return {
        "source": "Brunel University London scoping review",
        "sourceType": "Research finding",
        "locator": locator,
        "summary": summary,
        "url": BRUNEL_ARTICLE,
    }


SOURCE_REFERENCES = {
    "WHO-ITU-1": _who(1, "Telehealth platforms should work with assistive devices such as screen readers and Braille keyboards."),
    "WHO-ITU-2": _who(2, "Telehealth visits should offer contrast and magnification for viewing screen content."),
    "WHO-ITU-3": _who(3, "Telephone services should be accessible to people who cannot use the digital platform because of vision impairment."),
    "WHO-ITU-4": _who(4, "Telehealth apps should avoid unnecessary software downloads, platform switching, and differing passwords."),
    "WHO-ITU-5": _who(5, "Platform videos should avoid background music that masks relevant information."),
    "WHO-ITU-6": _who(6, "Video wording and descriptions should be clear and accurate."),
    "WHO-ITU-7": _who(7, "Video consultations should provide captions, monitored chat, and volume controls."),
    "WHO-ITU-8": _who(8, "Text messaging should remain available when video or audio communication fails."),
    "WHO-ITU-9": _who(9, "Remote sign-language interpretation should be available."),
    "WHO-ITU-10": _who(10, "Platform videos should provide readable subtitles and avoid masking background music."),
    "WHO-ITU-11": _who(11, "The video display should be large enough for lipreading."),
    "WHO-ITU-12": _who(12, "Platforms should support speech alternatives such as voice synthesis or text-to-speech."),
    "WHO-ITU-13": _who(13, "Virtual-visit controls should be large enough for people with limited fine-motor control."),
    "WHO-ITU-14": _who(14, "Telehealth platforms should not require fine-motor actions such as double clicking."),
    "WHO-ITU-15": _who(15, "Telehealth information should minimize scrolling and menu navigation."),
    "WHO-ITU-16": _who(16, "Platforms should avoid unexpected or irrelevant content that can cause distress."),
    "WHO-ITU-17": _who(17, "Platforms should explain their privacy and security measures."),
    "WHO-ITU-18": _who(18, "Platforms should avoid complex interfaces and language and provide task guidance."),
    "WHO-ITU-19": _who(19, "Platforms should avoid unnecessarily effortful tasks and unresolved malfunctions."),
    "WHO-ITU-20": _who(20, "Platforms should provide trustworthy, good-quality information."),
    "WHO-ITU-21": _who(21, "Health-care documents should be available in accessible formats, including easy-read formats."),
    "WHO-ITU-22": _who(22, "Telehealth meetings should allow a support person to join alongside the patient and provider."),
    "WHO-ITU-23": _who(23, "Platforms should offer simple materials explaining how to use telehealth services."),
    "WHO-ITU-24": _who(24, "Text and document layout should be accessible to people with dyslexia and other learning disabilities."),
    "WHO-ITU-25": _who(25, "Text should be understandable and users should have enough time to read and act."),
    "ETSI-5.9": _etsi("5.9", "An ICT mode requiring simultaneous actions should have an alternative without simultaneous actions.", 29),
    "ETSI-6.4": _etsi("6.4", "Voice-based communication tasks should have a way to be completed without hearing or speech.", 32),
    "ETSI-12.1.1": _etsi("12.1.1", "Product documentation should explain accessibility and compatibility features.", 84),
    "BRUNEL-NAVIGATION": _brunel("Abstract, p. 1", "Poor navigation is a reported web accessibility barrier."),
    "BRUNEL-FORMS": _brunel("Abstract, p. 1", "Complex web forms are a reported web accessibility barrier."),
    "BRUNEL-ALT-TEXT": _brunel("Abstract, p. 1", "Missing or unsuitable alternative text is a reported web accessibility barrier."),
}


def source_reference(reference_id):
    """Return the canonical display record for one catalog ID."""
    source = SOURCE_REFERENCES[reference_id]
    return {"id": reference_id, **source}
