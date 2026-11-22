"""Sentiment: four labels in English, Hindi and Hinglish, plus conversation tracking."""
import pytest

from paysetu_agent.sentiment_analysis import ConversationSentiment, analyze

CASES = [
    ("Thanks a lot, that was really helpful!", "Positive"),
    ("Dhanyavaad, problem solve ho gaya", "Positive"),
    ("धन्यवाद, बहुत बढ़िया", "Positive"),
    ("What is the daily UPI limit?", "Neutral"),
    ("Cashback kab milega?", "Neutral"),
    ("Hi", "Neutral"),
    ("My payment failed and money was deducted", "Negative"),
    ("Yaar 5 din ho gaye paise nahi aaye, bahut pareshan hoon", "Negative"),
    ("मेरा पेमेंट फेल हो गया लेकिन पैसे कट गए", "Negative"),
    ("I am not happy with this", "Negative"),
    ("This is the WORST app EVER!!! Useless service", "Angry"),
    ("Bakwas app hai, ghatiya service!!", "Angry"),
    ("बकवास सर्विस है, बेकार ऐप", "Angry"),
    ("Pathetic. Ridiculous. I'm fed up with you people", "Angry"),
]


@pytest.mark.parametrize("text,label", CASES)
def test_labels(text, label):
    assert analyze(text)["label"] == label, analyze(text)


def test_score_range_and_reasons():
    for text, _ in CASES:
        r = analyze(text)
        assert -1.0 <= r["score"] <= 1.0 and r["signals"]
    assert analyze("Thanks!")["score"] > 0 > analyze("payment failed, very worried")["score"]


def test_negation_is_understood():
    assert analyze("no problem at all, thank you")["label"] == "Positive"


def test_conversation_frustration():
    c = ConversationSentiment()
    assert not c.add(analyze("What is the daily UPI limit?"))["frustrated"]
    assert not c.add(analyze("My payment failed"))["frustrated"]
    s = c.add(analyze("still not received, very worried"))
    assert s["frustrated"] and "two negative" in s["why"]
    assert ConversationSentiment().add(analyze("WORST service EVER!!! useless"))["frustrated"]
