SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[loanUa]
		@loanId INT,
		@price NUMERIC(12, 2) = NULL,
		@loanStatus VARCHAR(100) = NULL,
		@analystComments VARCHAR(MAX) = NULL,
		@brokerId INT = NULL,
		@brokerFeePercentage NUMERIC(12, 3) = NULL,
		@loanAnalyst VARCHAR(100) = NULL
AS
BEGIN;


	DECLARE @loanStatusId INT = (SELECT MAX(pricing_status_id) 
								 FROM fnba.pricing_status 
								 WHERE pricing_status = @loanStatus
								);
	DECLARE @loanAnalystId INT = (SELECT MAX(assoc_id)
								  FROM perdb.fnba.associate
								  WHERE nickname = @loanAnalyst
								 );
	DECLARE @currentPrice NUMERIC(12, 2);
	DECLARE @currentLoanStatusId INT;
	DECLARE @currentAnalystComments VARCHAR(MAX);
	DECLARE @currentBrokerId INT;
	DECLARE @currentbrokerFeePercentage NUMERIC(12, 3);
	DECLARE @currentLoanAnalystId VARCHAR(100);
	DECLARE @bidId INT;

	BEGIN TRY;

		SET XACT_ABORT ON;
		BEGIN TRANSACTION;

		SELECT @loanStatus = NULLIF(LTRIM(RTRIM(@loanStatus)), ''),
			   @analystComments = NULLIF(LTRIM(RTRIM(@analystComments)), ''),
			   @brokerId = NULLIF(@brokerId, 0),
			   @brokerFeePercentage = NULLIF(@brokerFeePercentage, 0.00),
			   @loanAnalystId = NULLIF(@loanAnalystId, 0);

		SELECT @currentPrice = COALESCE(price, 0.00),
			   @currentLoanStatusId = COALESCE(loanStatusId, 0),
			   @currentBrokerId = COALESCE(brokerId, 0),
			   @currentbrokerFeePercentage = COALESCE(brokerFeePercentage, 0.00),
			   @bidId = bidId,
			   @currentLoanAnalystId = COALESCE(loanAnalystId, 0)
		FROM bid.loan
		WHERE loanId = @loanId;

		SELECT @currentAnalystComments = analystComments
		FROM bid.loan
		WHERE loanId = @loanId;

		IF(@price IS NOT NULL AND @price <> @currentPrice)
		BEGIN;
			UPDATE bid.loan
			SET price = @price,
				discount = (currentBalance - @price) / currentBalance,
				totalBid = (1 - (currentBalance - @price) / currentBalance) * 100
			WHERE loanId = @loanId;
		END;

		IF(@loanStatus IS NOT NULL AND @loanStatusId <> @currentLoanStatusId)
		BEGIN;
			UPDATE bid.loan
			SET loanStatusId = @loanStatusId
			WHERE loanId = @loanId;
		END;

		IF(@loanAnalystId IS NOT NULL AND @loanAnalystId <> @currentLoanAnalystId)
		BEGIN;
			UPDATE bid.loan
			SET loanAnalystId = @loanAnalystId
			WHERE loanId = @loanId;
		END;

		IF(@analystComments IS NOT NULL AND COALESCE(@currentAnalystComments, '') <> @analystComments)
		BEGIN;
			UPDATE bid.loan
			SET analystComments = @analystComments
			WHERE loanId = @loanId;

			IF(@@ROWCOUNT = 0)
			BEGIN;
				INSERT fnba.loan_text(pkg_purchase_id, pkg_purchase_loan_id, field_name, field_value)
				VALUES(@bidId, @loanId, 'analyst_comments', @analystComments)
			END;
		END;

		IF(@brokerId IS NOT NULL AND @brokerId <> @currentBrokerId)
		BEGIN;
			UPDATE bid.loan
			SET brokerId = @brokerId
			WHERE loanId = @loanId;

			IF(@@ROWCOUNT = 0)
			BEGIN;
				INSERT bid.loanBrokerFees(bidId, loanId, brokerId)
				VALUES(@loanId, @loanId, @brokerId);
			END;
		END;

		IF(@brokerFeePercentage IS NOT NULL AND @brokerFeePercentage <> @currentbrokerFeePercentage)
		BEGIN;
			UPDATE bid.loan
			SET brokerFeePercentage = @brokerFeePercentage
			WHERE loanId = @loanId;

			IF(@@ROWCOUNT = 0)
			BEGIN;
				INSERT bid.loanBrokerFees(bidId, loanId, brokerId, feePercentage)
				VALUES(@loanId, @loanId, @brokerId, @brokerFeePercentage);
			END;
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