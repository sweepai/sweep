using Microsoft.AspNetCore.Mvc;
using System.IO;
using System;
using Google.Apis.Drive.v3;
using Google.Apis.Auth.OAuth2;
using Google.Apis.Services;
using Google.Apis.Util.Store;
using System.Threading;

namespace RevisionMVC.Web.Controllers
{
    public class ExcelController : Controller
    {
        // Method for importing Excel files
        public IActionResult ImportExcel(IFormFile file)
        {
            // Logic for importing Excel files
            var filePath = Path.GetTempFileName();
        
            using (var stream = System.IO.File.Create(filePath))
            {
                file.CopyTo(stream);
            }
        
            return View();
        }

        // Method for exporting Excel files
        public IActionResult ExportExcel()
        {
            // Logic for exporting Excel files
            var fileStream = new MemoryStream();
        
            // Logic to populate the fileStream with Excel data goes here
        
            return new FileStreamResult(fileStream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        }

        // Method for giving unique names to the Excel files
        private string GetUniqueFileName(string fileName)
        {
            fileName = Path.GetFileName(fileName);
            return Path.GetFileNameWithoutExtension(fileName)
                   + "_" 
                   + Guid.NewGuid().ToString().Substring(0, 4) 
                   + Path.GetExtension(fileName);
        }

        // Method for uploading the Excel files to Google Drive
        public void UploadToGoogleDrive(string fileName, string filePath)
        {
            // Logic for uploading the Excel files to Google Drive
            var driveService = new DriveService(new BaseClientService.Initializer
            {
                HttpClientInitializer = GetCredential(),
                ApplicationName = "RevisionMVC.Web",
            });
        
            var fileMetadata = new Google.Apis.Drive.v3.Data.File()
            {
                Name = Path.GetFileName(filePath),
            };
        
            FilesResource.CreateMediaUpload request;
        
            using (var stream = new System.IO.FileStream(filePath, System.IO.FileMode.Open))
            {
                request = driveService.Files.Create(fileMetadata, stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                request.Fields = "id";
                request.Upload();
            }
        }
    }
}