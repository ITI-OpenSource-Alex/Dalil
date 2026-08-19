"""Frozen IELTS Writing rubric rendered directly into scoring prompts.

The wording is a compact transcription of the public IELTS Writing Band
Descriptors updated May 2023.  All bands are present: a scorer never has to
invent or recall the missing lower half of the scale.
Source: https://ielts.org/cdn/Guides/ielts-writing-band-descriptors.pdf
"""

from __future__ import annotations

from typing import Literal


Criterion = Literal["task_response", "cohesion", "vocabulary", "grammar"]

RUBRIC_ID = "ielts-writing-public"
RUBRIC_VERSION = "2023-05"


TASK2_TASK_RESPONSE = {
    9: "Prompt explored in depth; fully developed position directly answers it; relevant ideas are fully extended and supported; lapses are extremely rare.",
    8: "Prompt sufficiently addressed; clear, well-developed position; relevant ideas are well extended and supported; only occasional omissions or lapses.",
    7: "Main prompt parts addressed; clear, developed position; ideas are extended and supported, with possible over-generalisation or limited focus/precision.",
    6: "Main prompt parts addressed, unevenly at times; relevant position, but conclusions may be unclear, unjustified, or repetitive; some ideas/support lack development, clarity, or relevance.",
    5: "Main prompt parts incompletely addressed; position exists but development is not always clear; ideas are limited, insufficiently developed, repetitive, or include irrelevant detail.",
    4: "Prompt tackled minimally or tangentially; position is hard to identify; ideas are difficult to identify and may lack relevance, clarity, or support; large parts may repeat.",
    3: "No prompt part adequately addressed or prompt misunderstood; no relevant position; few ideas, often irrelevant or insufficiently developed.",
    2: "Content barely relates to prompt; no identifiable position; only glimpses of undeveloped ideas or an off-topic response.",
    1: "Twenty words or fewer, wholly unrelated content, or copied rubric after copied material is discounted.",
    0: "No attempt, non-English throughout, or proven totally memorised answer.",
}

TASK1_TASK_ACHIEVEMENT = {
    9: "All task requirements fully and appropriately satisfied; content lapses are extremely rare.",
    8: "Task sufficiently covered; Academic key features are skilfully selected, clearly presented, highlighted and illustrated; General Training bullet points are clearly presented, extended, with clear purpose and appropriate tone; only occasional lapses.",
    7: "Requirements covered with relevant, accurate content and appropriate format; Academic response has a clear overview, categorised data, and main trends/differences; General Training covers all bullet points with clear purpose and consistently appropriate tone; minor lapses only.",
    6: "Focuses on requirements in an appropriate format; Academic key features are adequately highlighted with a relevant overview and supported data; General Training covers all bullet points with generally clear purpose and minor tone inconsistencies; some detail may be missing, excessive, irrelevant, or inaccurate.",
    5: "Generally addresses task, but format may lapse; Academic key features are inadequately covered or mechanically recounted, possibly without data; General Training covers bullet points inadequately with sometimes unclear purpose or variable tone; limited extension and distracting inaccuracies may occur.",
    4: "Attempts task but selects few Academic key features or omits General Training bullet points; purpose/tone/format may be unclear or inappropriate; presented content may be irrelevant, repetitive, or inaccurate.",
    3: "Does not address task requirements, perhaps through misunderstanding; presented key features or bullet points are largely irrelevant; little repetitive information.",
    2: "Content barely relates to task; little relevant message or wholly off-topic response.",
    1: "Twenty words or fewer, wholly unrelated content, or copied rubric after copied material is discounted.",
    0: "No attempt, non-English throughout, or proven totally memorised answer.",
}

COHESION = {
    9: "Message is effortless to follow; cohesion almost never attracts attention; lapses are minimal; paragraphing is skilfully managed.",
    8: "Message is easy to follow; ideas are logically sequenced and cohesion well managed; occasional lapses; paragraphing is sufficient and appropriate.",
    7: "Ideas are logically organised with clear progression; cohesive devices, reference, and substitution are flexible despite minor inaccuracies or over/under-use; paragraphs effectively support coherence.",
    6: "Ideas are generally coherent with clear overall progression; cohesion has some good effect but may be faulty or mechanical; reference/substitution may lack clarity; paragraph logic or central topics may lapse.",
    5: "Organisation is evident but not wholly logical and progression may be weak; ideas can be followed but are not fluently linked; cohesion/reference may be limited, inaccurate, overused, or repetitive; paragraphing may be inadequate.",
    4: "Ideas are not coherently arranged and lack clear progression; relationships are unclear or inadequately marked; basic cohesion may be inaccurate/repetitive; referencing and paragraph topics are weak or absent.",
    3: "No apparent logical organisation; ideas are hard to relate; minimal sequencing/cohesion does not reliably show logical relationships; referencing and paragraphing are unhelpful.",
    2: "Little evidence of control of organisational features.",
    1: "Twenty words or fewer; writing communicates no message and appears to be from a virtual non-writer.",
    0: "No attempt, non-English throughout, or proven totally memorised answer.",
}

VOCABULARY = {
    9: "Full flexibility and precision; wide vocabulary used accurately and appropriately with natural, sophisticated control; spelling/word-formation slips are extremely rare and minimally affect communication.",
    8: "Wide resource used fluently and flexibly for precise meaning; uncommon/idiomatic items used skilfully despite occasional choice/collocation inaccuracies; spelling/word-formation errors are occasional and minimally affect communication.",
    7: "Enough resource for flexibility and precision; some less common/idiomatic use with awareness of style and collocation; only a few spelling/word-formation errors that do not reduce clarity.",
    6: "Generally adequate and appropriate resource; meaning remains clear despite restricted range or imprecision; risk-taking may widen range with more inaccuracies; spelling/word-formation errors do not impede communication.",
    5: "Limited but minimally adequate resource; accurate simple vocabulary but little variation; frequent inappropriate choices, simplification, or repetition; spelling/word-formation errors may trouble the reader.",
    4: "Limited, inadequate, or task-unrelated resource; basic repetitive vocabulary and inappropriate memorised/formulaic chunks; word choice, formation, or spelling may impede meaning.",
    3: "Inadequate resource, possibly due to severe underlength; dependence on input/memorised language; very limited word-choice/spelling control with errors that may severely impede meaning.",
    2: "Extremely limited resource with few recognisable strings beyond memorised phrases; no apparent word-formation or spelling control.",
    1: "Twenty words or fewer; no resource beyond a few isolated words.",
    0: "No attempt, non-English throughout, or proven totally memorised answer.",
}

GRAMMAR = {
    9: "Wide range of structures with full flexibility and control; grammar and punctuation appropriate throughout; minor errors extremely rare with minimal impact.",
    8: "Wide range used flexibly and accurately; most sentences error-free and punctuation well managed; occasional non-systematic errors minimally affect communication.",
    7: "Variety of complex structures with some flexibility and accuracy; grammar/punctuation generally controlled and error-free sentences frequent; persistent errors do not impede communication.",
    6: "Mix of simple and complex forms with limited flexibility; complex structures are less accurate than simple ones; grammar/punctuation errors rarely impede communication.",
    5: "Limited, repetitive range; attempted complex sentences are often faulty while simple sentences are most accurate; frequent grammar errors and faulty punctuation may trouble the reader.",
    4: "Very limited range dominated by simple sentences; subordinate clauses are rare; some accurate structures, but frequent grammar and punctuation errors may impede meaning.",
    3: "Sentence forms attempted, but grammar/punctuation errors predominate and prevent most meaning; length may provide insufficient evidence of control.",
    2: "Little or no evidence of sentence forms beyond memorised phrases.",
    1: "Twenty words or fewer; no rateable language is evident.",
    0: "No attempt, non-English throughout, or proven totally memorised answer.",
}


def descriptors_for(criterion: Criterion, task_number: int) -> dict[int, str]:
    if criterion == "task_response":
        return TASK1_TASK_ACHIEVEMENT if task_number == 1 else TASK2_TASK_RESPONSE
    if criterion == "cohesion":
        return COHESION
    if criterion == "vocabulary":
        return VOCABULARY
    return GRAMMAR


def descriptor_label(criterion: Criterion, task_number: int) -> str:
    return (
        "task_achievement"
        if criterion == "task_response" and task_number == 1
        else criterion
    )


def allowed_descriptor_ids(criterion: Criterion, task_number: int) -> set[str]:
    label = descriptor_label(criterion, task_number)
    return {f"{label}.{band}" for band in descriptors_for(criterion, task_number)}


def render_descriptors(criterion: Criterion, task_number: int) -> str:
    label = descriptor_label(criterion, task_number)
    lines = [
        f"FROZEN RUBRIC: {RUBRIC_ID}/{RUBRIC_VERSION}; criterion={label}",
        "Use only these descriptors. Compare the chosen band with both adjacent bands.",
    ]
    for band, descriptor in descriptors_for(criterion, task_number).items():
        lines.append(f"[{label}.{band}] Band {band}: {descriptor}")
    return "\n".join(lines)
