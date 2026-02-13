SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE PROCEDURE [bid].[bidUa] @bidId INT, @sellerId INT
AS
BEGIN;

	BEGIN TRY;

		DECLARE @currentSellerId INT;

		SET XACT_ABORT ON;
		BEGIN TRANSACTION;

		SELECT @sellerId = NULLIF(@sellerId, 0);

		SELECT @currentSellerId = COALESCE(seller_id, 0)
		FROM fnba.pkg_purchase 
		WHERE pkg_purchase_id = @bidId;

		IF(@sellerId IS NOT NULL AND @sellerId <> @currentSellerId)
		BEGIN;
			UPDATE fnba.pkg_purchase
			SET seller_id = @sellerId
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