package interview

import "strings"

const (
	introScript   = "Good morning. This is your IELTS-style speaking practice. When you are ready, we will begin with some questions about you."
	part2Script   = "Now I am going to give you a topic. You will have one minute to prepare, and then you should speak for one to two minutes."
	part3Script   = "We have been talking about this topic. Now I would like to discuss some more general questions related to it."
	closingScript = "That is the end of the speaking practice. Thank you."
)

func cueCardScript(cue CueCard) string {
	var text strings.Builder
	text.WriteString(cue.Topic)
	text.WriteString(" You should say ")
	text.WriteString(strings.Join(cue.Prompts, "; "))
	text.WriteString("; ")
	text.WriteString(cue.ClosingPrompt)
	text.WriteString(".")
	return text.String()
}

func partLabel(part int) string {
	switch part {
	case 1:
		return "Introduction and interview"
	case 2:
		return "Long turn"
	case 3:
		return "Discussion"
	default:
		return ""
	}
}
