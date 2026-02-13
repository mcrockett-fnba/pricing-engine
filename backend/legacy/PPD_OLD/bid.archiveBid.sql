SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE PROCEDURE [bid].[archiveBid] @bidId INT
AS
BEGIN;

	UPDATE fnba.pkg_purchase
	SET isActiveBid = 0
	WHERE pkg_purchase_id = @bidId;

END;
GO