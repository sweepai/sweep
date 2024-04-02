#include "stdafx.h"
#include "ExportedFunctions.h"
#include "RegisterIoTThing.h"
#include "IoTPubSub.h"
#include "IoTTest.h"
#include "Constants.h"

std::string CopyInput(LPCWSTR input) {
	std::string s;

#ifdef UNICODE
	std::wstring w;
	w = input;
	s = std::string(w.begin(), w.end());
#else
	s = input;
#endif
	return s;
}

int __stdcall RegisterIoTThing(
	LPCWSTR tenantID,
	LPCWSTR iotName,
	LPCWSTR certificatePemLocation,
	LPCWSTR privateKeyLocation,
	LPCWSTR lanGuardRole,
	LPCWSTR certificateId,
	LPCWSTR certificatesRootPath
)
{
	try {
		if (IsBadStringPtrW(tenantID, MAX_INPUT_LENGTH) || 
			IsBadStringPtrW(iotName, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(certificatePemLocation, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(privateKeyLocation, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(lanGuardRole, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(certificateId, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(certificatesRootPath, MAX_INPUT_LENGTH))
		{
			return CODE_ERROR_BAD_STRING;
		}

		CRegisterIoTThing registerIoTThing;
		registerIoTThing.RegisterIoTThing(
			CopyInput(tenantID),
			CopyInput(iotName),
			CopyInput(certificatePemLocation),
			CopyInput(privateKeyLocation),
			CopyInput(lanGuardRole),
			CopyInput(certificateId),
			CopyInput(certificatesRootPath)
		);
		return CODE_SUCCESS;
	}
	catch (...) {
		return CODE_ERROR_UNKNOWN;
	}
}

int __stdcall IoTTestClient(
	LPCWSTR tenantID,
	LPCWSTR iotName,
	LPCWSTR certificatePemLocation,
	LPCWSTR privateKeyLocation,
	LPCWSTR message,
	BOOL    silent,
	BOOL    connectOnly
)
{
	try {
		if (IsBadStringPtrW(tenantID, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(iotName, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(certificatePemLocation, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(privateKeyLocation, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(message, MAX_INPUT_LENGTH))
		{
			return CODE_ERROR_BAD_STRING;
		}

		CIoTTest ioTTest(!!silent);
		if (!connectOnly)
		{
			return ioTTest.IoTTestClient(
				CopyInput(tenantID),
				CopyInput(iotName),
				CopyInput(certificatePemLocation),
				CopyInput(privateKeyLocation),
				CopyInput(message)
			);
		}

		return ioTTest.IoTTestConnection(
			CopyInput(tenantID),
			CopyInput(iotName),
			CopyInput(certificatePemLocation),
			CopyInput(privateKeyLocation)
		);
	}
	catch (...) {
		return CODE_ERROR_UNKNOWN;
	}
}

// AI-GEN START - Cursor
int __stdcall IoTTestProvisionedCertificate(
	LPCWSTR tenantID,
	LPCWSTR iotName,
	LPCWSTR certificatePemLocation,
	LPCWSTR privateKeyLocation,
	LPCWSTR certificateId,
	LPCWSTR message,
	BOOL    silent,
	BOOL    connectOnly
)
{
	CRegisterIoTThing registerIoTThing;
	int result = registerIoTThing.RegisterIoTThing(
		CopyInput(tenantID),
		CopyInput(iotName),
		CopyInput(certificatePemLocation),
		CopyInput(privateKeyLocation),
		CFG_WAN_LANGUARD_TEST_ROLE_AGENT,
		CopyInput(certificateId),
		std::string(DEFAULT_PATH_CERTIFICATES) + "\\" + std::string(CA_CERTIFICATE_FILENAME));
	if (result != CODE_SUCCESS) {
		return result;
	}

	// IOTPUBSUB connect
	result = IOTPUBSUB.ConnectClient(CopyInput(tenantID), CopyInput(iotName));
	if (result != CODE_SUCCESS) {
		return result;
	}

	// IOTPUBSUB subcribe
	if ((IOTPUBSUB.SubscribeClient(CopyInput(tenantID), CopyInput(iotName))!= CODE_SUCCESS) ||
	(IOTPUBSUB.SubscribeClient(IOT_JOBS_TEST_TOPIC_PREFIX + CopyInput(tenantID), CFG_WAN_AGENT_JOBS_TEST_NOTIFY_TOPIC)!= CODE_SUCCESS) ||
	(IOTPUBSUB.SubscribeClient(IOT_JOBS_TEST_TOPIC_PREFIX + CopyInput(tenantID), CFG_WAN_AGENT_JOBS_TEST_NOTIFYNEXT_TOPIC)!= CODE_SUCCESS)) {
		return CODE_ERROR_SUBSCRIPTION_FAILED;
	}

	return IOTPUBSUB.DisconnectClient();
}
// AI-GEN END

int __stdcall PublishMessage(
	LPCWSTR tenantID,
	LPCWSTR iotName,
	LPCWSTR targetIotName,
	LPCWSTR message
)
{
	try {
		if (IsBadStringPtrW(tenantID, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(iotName, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(targetIotName, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(message, MAX_INPUT_LENGTH))
		{
			return CODE_ERROR_BAD_STRING;
		}

		IOTPUBSUB.PublishMessageNewConnection(
			CopyInput(tenantID),
			CopyInput(iotName),
			CopyInput(targetIotName),
			CopyInput(message)
		);
		return CODE_SUCCESS;
	}
	catch (...) {
		return CODE_ERROR_UNKNOWN;
	}
}

int __stdcall GetControlPlaneCredentials(
	LPCSTR iotName,
	LPCSTR certificatePemLocation,
	LPCSTR privateKeyLocation,
	LPSTR controlPlaneAccessKey,
	LPSTR controlPlaneSecretKey,
	LPSTR controlPlaneSessionToken
)
{
	try {
		if (IsBadStringPtrA(iotName, MAX_INPUT_LENGTH) ||
			IsBadStringPtrA(certificatePemLocation, MAX_INPUT_LENGTH) ||
			IsBadStringPtrA(privateKeyLocation, MAX_INPUT_LENGTH))
		{
			return CODE_ERROR_BAD_STRING;
		}

		IOTPUBSUB.ConfigureCredentialsProvider(
			std::string(iotName),
			std::string(certificatePemLocation),
			std::string(privateKeyLocation)
		);
		if (IOTPUBSUB.GetTempCredentialsFromIoTProvider() == 0)
		{
			std::string cpAccessKey = IOTPUBSUB.getControlPlaneAccessKey();
			std::copy(cpAccessKey.begin(), cpAccessKey.end(), controlPlaneAccessKey);
			controlPlaneAccessKey[cpAccessKey.size()] = 0;

			std::string cpSecretKey = IOTPUBSUB.getControlPlaneSecretKey();
			std::copy(cpSecretKey.begin(), cpSecretKey.end(), controlPlaneSecretKey);
			controlPlaneSecretKey[cpSecretKey.size()] = 0;

			std::string cpSessionToken = IOTPUBSUB.getControlPlaneSessionToken();
			std::copy(cpSessionToken.begin(), cpSessionToken.end(), controlPlaneSessionToken);
			controlPlaneSessionToken[cpSessionToken.size()] = 0;

			return CODE_SUCCESS;
		}
		return CODE_ERROR_TEMPAWSCREDENTIALS_GENERATION_FAILED;
	}
	catch (...) {
		return CODE_ERROR_UNKNOWN;
	}
}

int __stdcall UploadScanResultsToS3(
	LPCWSTR s3PreSignedUrl,
	LPCWSTR scanResultsPath
)
{
	try {
		if (IsBadStringPtrW(s3PreSignedUrl, MAX_INPUT_LENGTH) ||
			IsBadStringPtrW(scanResultsPath, MAX_INPUT_LENGTH))
		{
			return CODE_ERROR_BAD_STRING;
		}

		if (IOTPUBSUB.UploadScanResultsToS3(
			CopyInput(s3PreSignedUrl),
			CopyInput(scanResultsPath)))
		{
			return CODE_SUCCESS;
		}
		return CODE_ERROR_UPLOAD_FAILED;
	}
	catch (...) {
		return CODE_ERROR_UNKNOWN;
	}
}