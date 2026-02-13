SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE PROCEDURE [bid].[assignCommitmentNumber]
	@bidId INT
AS 
BEGIN;

	DECLARE @commitmentNumber INT;

	BEGIN TRY;

		SET XACT_ABORT ON;
		BEGIN TRANSACTION;

		SELECT @commitmentNumber = commitmentNumber
		FROM fnba.pkg_purchase
		WHERE pkg_purchase_id = @bidId;

		IF(@commitmentNumber IS NULL)
		BEGIN;
			SELECT @commitmentNumber = COALESCE(MAX(commitmentNumber), 2999) + 1
			FROM fnba.pkg_purchase
		
			UPDATE fnba.pkg_purchase
			SET commitmentNumber = @commitmentNumber
			WHERE pkg_purchase_id = @bidId;
		END;

		COMMIT TRANSACTION;

	END TRY
	BEGIN CATCH
		
		DECLARE @message VARCHAR(MAX) = ERROR_MESSAGE();
		IF(@@TRANCOUNT > 0) ROLLBACK TRANSACTION;
		THROW 50000, @message, 1;

	END CATCH;

END;
GO