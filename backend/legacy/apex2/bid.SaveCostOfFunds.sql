SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[SaveCostOfFunds]
		@pkgPurchaseId INT,
		@costOfFunds DECIMAL(12, 7)
AS
BEGIN;

	DECLARE @savedCostOfFunds DECIMAL(12, 4);

	BEGIN TRY;

		SET XACT_ABORT ON;
		BEGIN TRANSACTION;

		SELECT @savedCostOfFunds = ISNULL(costOfFunds, 0.00)
		FROM fnba.pkg_purchase
		WHERE pkg_purchase_id = @pkgPurchaseId;

		IF(ISNULL(@costOfFunds, 0.00) <> @savedCostOfFunds)
		BEGIN;
			UPDATE fnba.pkg_purchase
			SET costOfFunds = @costOfFunds
			WHERE pkg_purchase_id = @pkgPurchaseId;

			UPDATE fnba.pkg_purchase_loan
			SET costOfFunds = @costOfFunds
			WHERE pkg_purchase_id = @pkgPurchaseId;
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