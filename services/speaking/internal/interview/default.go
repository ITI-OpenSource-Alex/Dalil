package interview

import _ "embed"

//go:embed bank/ielts-speaking-bank-2026-08.json
var defaultBankJSON []byte

func LoadDefaultBank() (*Bank, error) {
	return LoadBank(defaultBankJSON)
}
